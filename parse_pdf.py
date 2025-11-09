#!/usr/bin/env python3
"""
PDF Paragraph Splitter
Splits PDF content into sections based on table of contents or main paragraphs
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple
from pypdf import PdfReader


class PDFSplitter:
    def __init__(self, pdf_path: str):
        """Initialize with PDF file path"""
        self.pdf_path = Path(pdf_path)
        self.reader = PdfReader(str(self.pdf_path))
        self.total_pages = len(self.reader.pages)
        
    def extract_toc(self) -> List[Dict]:
        """
        Extract table of contents from PDF outline/bookmarks
        Returns list of dicts with title, page_number
        """
        toc = []
        try:
            outlines = self.reader.outline
            if outlines:
                toc = self._parse_outline(outlines)
        except Exception as e:
            print(f"No TOC found or error extracting: {e}")
        
        return toc
    
    def _parse_outline(self, outlines, level=0) -> List[Dict]:
        """Recursively parse PDF outline structure"""
        toc = []
        for item in outlines:
            if isinstance(item, list):
                # Nested outline
                toc.extend(self._parse_outline(item, level + 1))
            else:
                # Outline item
                try:
                    page_num = self.reader.get_destination_page_number(item)
                    toc.append({
                        'title': item.title,
                        'page': page_num,
                        'level': level
                    })
                except Exception as e:
                    print(f"Could not get page for outline item: {e}")
        return toc
    
    def extract_text_by_page(self) -> List[str]:
        """Extract text from each page"""
        pages_text = []
        for page_num in range(self.total_pages):
            page = self.reader.pages[page_num]
            text = page.extract_text()
            pages_text.append(text)
        return pages_text
    
    def split_by_toc(self) -> List[Dict]:
        """
        Split PDF content based on table of contents
        Returns list of sections with title, content, start_page, end_page
        """
        toc = self.extract_toc()
        
        if not toc:
            print("No TOC found, falling back to paragraph-based splitting")
            return self.split_by_paragraphs()
        
        print(f"Found {len(toc)} sections in TOC")
        
        # Get all text by page
        pages_text = self.extract_text_by_page()
        
        sections = []
        for i, item in enumerate(toc):
            start_page = item['page']
            # End page is the start of next section, or last page
            end_page = toc[i + 1]['page'] if i + 1 < len(toc) else self.total_pages
            
            # Collect content from start to end page
            content = []
            for page_num in range(start_page, end_page):
                if page_num < len(pages_text):
                    content.append(pages_text[page_num])
            
            sections.append({
                'title': item['title'],
                'level': item.get('level', 0),
                'start_page': start_page + 1,  # Human-readable page numbers
                'end_page': end_page,
                'content': '\n\n'.join(content).strip()
            })
        
        return sections
    
    def split_by_paragraphs(self) -> List[Dict]:
        """
        Split PDF by detecting main paragraphs/sections
        Uses heuristics: large fonts, capitalization, numbering
        """
        pages_text = self.extract_text_by_page()
        full_text = '\n\n'.join(pages_text)
        
        # Split by multiple newlines (paragraphs)
        paragraphs = re.split(r'\n\s*\n+', full_text)
        
        sections = []
        section_num = 1
        current_section = []
        current_title = None
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Detect if this looks like a heading
            is_heading = self._is_likely_heading(para)
            
            if is_heading:
                # Save previous section if exists
                if current_section:
                    sections.append({
                        'title': current_title or f"Section {section_num}",
                        'level': 0,
                        'content': '\n\n'.join(current_section).strip()
                    })
                    section_num += 1
                
                # Start new section
                current_title = para[:100]  # Limit title length
                current_section = []
            else:
                current_section.append(para)
        
        # Add last section
        if current_section:
            sections.append({
                'title': current_title or f"Section {section_num}",
                'level': 0,
                'content': '\n\n'.join(current_section).strip()
            })
        
        return sections
    
    def _is_likely_heading(self, text: str) -> bool:
        """
        Heuristic to detect if text is likely a heading
        """
        if len(text) > 200:  # Too long for a heading
            return False
        
        # Check for common heading patterns
        heading_patterns = [
            r'^\d+\.?\s+[A-Z]',  # Numbered: "1. Introduction" or "1 Introduction"
            r'^[A-Z][A-Z\s]{3,}$',  # ALL CAPS
            r'^Chapter\s+\d+',  # Chapter X
            r'^Section\s+\d+',  # Section X
            r'^[IVXLCDM]+\.\s+[A-Z]',  # Roman numerals: "I. Introduction"
        ]
        
        for pattern in heading_patterns:
            if re.match(pattern, text.strip()):
                return True
        
        # Check if mostly uppercase and short
        words = text.split()
        if len(words) <= 10:  # Short text
            uppercase_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
            if uppercase_ratio > 0.6:  # Mostly uppercase
                return True
        
        return False
    
    def create_document_summary(self, sections: List[Dict]) -> str:
        """
        Create a comprehensive document summary optimized for Claude context
        """
        summary_parts = []
        
        # Document overview
        summary_parts.append("# DOCUMENT STRUCTURE SUMMARY")
        summary_parts.append(f"Total Sections: {len(sections)}")
        summary_parts.append(f"Total Pages: {self.total_pages}\n")
        
        # Table of contents
        summary_parts.append("## TABLE OF CONTENTS")
        for i, section in enumerate(sections, 1):
            indent = "  " * section.get('level', 0)
            pages = ""
            if 'start_page' in section:
                pages = f" [p.{section['start_page']}-{section['end_page']}]"
            summary_parts.append(f"{indent}{i}. {section['title']}{pages}")
        
        summary_parts.append("\n## SECTION SUMMARIES\n")
        
        # Create summaries for each section
        for i, section in enumerate(sections, 1):
            summary_parts.append(f"### Section {i}: {section['title']}")
            
            if 'start_page' in section:
                summary_parts.append(f"**Location:** Pages {section['start_page']}-{section['end_page']}")
            
            # Extract key information
            content = section['content']
            word_count = len(content.split())
            char_count = len(content)
            
            summary_parts.append(f"**Length:** {word_count} words, {char_count} characters")
            
            # Extract first paragraph as preview
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            if paragraphs:
                preview = paragraphs[0][:300]
                if len(paragraphs[0]) > 300:
                    preview += "..."
                summary_parts.append(f"**Preview:** {preview}")
            
            # Extract key sentences (heuristic: sentences with numbers, quotes, or important keywords)
            key_sentences = self._extract_key_sentences(content, max_sentences=3)
            if key_sentences:
                summary_parts.append("**Key Points:**")
                for sentence in key_sentences:
                    summary_parts.append(f"- {sentence}")
            
            summary_parts.append("")  # Blank line between sections
        
        # Add instructions for Claude
        summary_parts.append("\n## HOW TO USE THIS DOCUMENT")
        summary_parts.append("This summary provides the structure and overview of the full document.")
        summary_parts.append("Each section has been extracted to a separate file in the output directory.")
        summary_parts.append("To analyze specific sections in detail, refer to the individual section files.")
        summary_parts.append("Section numbers correspond to the filenames (e.g., Section 1 → 01_*.txt)")
        
        return '\n'.join(summary_parts)
    
    def _extract_key_sentences(self, text: str, max_sentences: int = 3) -> List[str]:
        """
        Extract potentially important sentences using heuristics
        """
        # Split into sentences (simple approach)
        sentences = re.split(r'[.!?]+\s+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        if not sentences:
            return []
        
        # Score sentences based on importance indicators
        scored_sentences = []
        for sentence in sentences[:50]:  # Only check first 50 sentences
            score = 0
            
            # Contains numbers (often important data/facts)
            if re.search(r'\d+', sentence):
                score += 2
            
            # Contains quotes
            if '"' in sentence or "'" in sentence:
                score += 1
            
            # Contains important keywords
            important_words = [
                'result', 'conclusion', 'found', 'significant', 'important',
                'demonstrate', 'show', 'indicate', 'suggest', 'recommend',
                'key', 'main', 'primary', 'critical', 'essential'
            ]
            for word in important_words:
                if word in sentence.lower():
                    score += 1
            
            # Not too long, not too short
            if 50 < len(sentence) < 200:
                score += 1
            
            scored_sentences.append((score, sentence))
        
        # Sort by score and get top sentences
        scored_sentences.sort(reverse=True, key=lambda x: x[0])
        top_sentences = [s[1] for s in scored_sentences[:max_sentences] if s[0] > 0]
        
        return top_sentences
    
    def save_sections(self, sections: List[Dict], output_dir: str = "output"):
        """Save sections to separate text files and create summary"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Save individual sections
        for i, section in enumerate(sections, 1):
            # Clean filename
            title = section['title']
            filename = re.sub(r'[^\w\s-]', '', title)[:50]
            filename = re.sub(r'[-\s]+', '_', filename)
            filepath = output_path / f"{i:02d}_{filename}.txt"
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Title: {section['title']}\n")
                if 'start_page' in section:
                    f.write(f"Pages: {section['start_page']}-{section['end_page']}\n")
                f.write(f"\n{'='*80}\n\n")
                f.write(section['content'])
            
            print(f"Saved: {filepath}")
        
        # Create and save document summary
        print("\nCreating document summary...")
        summary = self.create_document_summary(sections)
        summary_path = output_path / "00_DOCUMENT_SUMMARY.txt"
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        print(f"Saved summary: {summary_path}")
        
        # Also create a Claude-optimized context file
        context_path = output_path / "00_CLAUDE_CONTEXT.md"
        with open(context_path, 'w', encoding='utf-8') as f:
            f.write("# Document Context for Claude\n\n")
            f.write("**Instructions:** Upload this file first to give Claude context about the document structure, ")
            f.write("then upload specific section files for detailed analysis.\n\n")
            f.write("---\n\n")
            f.write(summary)
        
        print(f"Saved Claude context: {context_path}")


def main():
    """Main execution"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pdf_splitter.py <pdf_file> [output_dir]")
        sys.exit(1)
    
    pdf_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output"
    
    print(f"Processing: {pdf_file}")
    print(f"Output directory: {output_dir}")
    print("-" * 80)
    
    splitter = PDFSplitter(pdf_file)
    
    # Try splitting by TOC first
    sections = splitter.split_by_toc()
    
    print(f"\nFound {len(sections)} sections")
    print("-" * 80)
    
    # Display section info
    for i, section in enumerate(sections, 1):
        pages_info = ""
        if 'start_page' in section:
            pages_info = f" (pages {section['start_page']}-{section['end_page']})"
        print(f"{i}. {section['title']}{pages_info}")
        print(f"   Content length: {len(section['content'])} characters")
    
    # Save to files
    print("\n" + "-" * 80)
    print("Saving sections...")
    splitter.save_sections(sections, output_dir)
    print("\nDone!")


if __name__ == "__main__":
    main()

