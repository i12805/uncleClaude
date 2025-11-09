#!/usr/bin/env python3
"""
Interactive Claude PDF Analyzer
Analyze PDF sections using Claude API with prompt caching
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional
import anthropic


class ClaudePDFAnalyzer:
    # Preset system prompt templates
    PRESET_PROMPTS = {
        'generic': """You are an expert document analyzer. You have been provided with a document structure summary. Answer questions clearly and cite specific sections when relevant.""",
        
        'research': """You are a senior research analyst and peer reviewer with 20 years of experience in academic research.

When analyzing documents:
- Critically evaluate methodology and experimental design
- Assess statistical validity and significance
- Identify potential biases and confounding factors
- Check reproducibility and data transparency
- Rate evidence strength and quality
- Highlight gaps in reasoning or evidence
- Always cite specific page numbers and sections

Be constructively critical while remaining objective.""",
        
        'legal': """You are a senior legal analyst specializing in contract and document review.

Focus on:
- Key obligations, rights, and liabilities
- Ambiguous or unclear language
- Potential legal risks and exposure
- Missing or incomplete provisions
- Conflicting or contradictory clauses
- Compliance and regulatory implications
- Definitions and their scope

Use precise legal terminology and cite specific sections, pages, and clause numbers.""",
        
        'business': """You are a strategic business consultant and MBA with expertise in business analysis.

Analyze documents for:
- Key metrics, KPIs, and financial data
- Market opportunities and competitive positioning
- Strategic strengths and weaknesses
- Operational risks and challenges
- Growth drivers and barriers
- Actionable recommendations
- ROI and value propositions

Present insights in clear, executive-friendly language with data-driven support.""",
        
        'technical': """You are a senior software architect and technical lead with 15+ years of experience.

When reviewing technical documentation:
- Evaluate architecture and design patterns
- Identify implementation gaps and inconsistencies
- Assess scalability, performance, and security considerations
- Check for best practices and anti-patterns
- Flag potential technical debt and maintenance issues
- Verify API contracts and interface definitions
- Suggest improvements with specific examples
- Consider edge cases and error handling

Provide code examples, pseudo-code, or diagrams when relevant. Reference specific sections and page numbers.""",
        
        'medical': """You are a medical research analyst with expertise in clinical documentation and evidence-based medicine.

When analyzing medical documents:
- Evaluate clinical methodology and patient selection
- Assess endpoint definitions and measurement validity
- Check for adverse events and safety reporting
- Verify statistical approaches and power calculations
- Identify conflicts of interest or bias
- Rate evidence quality (GRADE criteria when applicable)
- Consider clinical significance vs statistical significance
- Always cite specific sections and page numbers

Note: Provide analytical insights only, not medical advice."""
    }
    
    def __init__(self, api_key: Optional[str] = None, mode: str = 'generic', custom_prompt: Optional[str] = None):
        """Initialize with Anthropic API key and analysis mode"""
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter"
            )
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.document_context = None
        self.conversation_history = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.cache_creation_tokens = 0
        self.cache_read_tokens = 0
        
        # Set system prompt
        if custom_prompt:
            self.system_prompt = custom_prompt
            self.current_mode = 'custom'
        else:
            self.set_mode(mode)
    
    def set_mode(self, mode: str):
        """Set analysis mode with preset prompt"""
        if mode not in self.PRESET_PROMPTS:
            available = ', '.join(self.PRESET_PROMPTS.keys())
            raise ValueError(f"Invalid mode '{mode}'. Available modes: {available}")
        
        self.system_prompt = self.PRESET_PROMPTS[mode]
        self.current_mode = mode
        print(f"✓ Analysis mode set to: {mode}\n")
    
    def set_custom_prompt(self, prompt: str):
        """Set a custom system prompt"""
        self.system_prompt = prompt
        self.current_mode = 'custom'
        print(f"✓ Custom system prompt set ({len(prompt)} characters)\n")
    
    def get_available_modes(self) -> List[str]:
        """Get list of available preset modes"""
        return list(self.PRESET_PROMPTS.keys())
    
    def show_current_mode(self):
        """Display current analysis mode and prompt"""
        print(f"\nCurrent mode: {self.current_mode}")
        print(f"System prompt preview (first 200 chars):")
        print(f"  {self.system_prompt[:200]}...")
        print()
        
    def load_context(self, context_file: str):
        """Load document summary/context file"""
        context_path = Path(context_file)
        if not context_path.exists():
            raise FileNotFoundError(f"Context file not found: {context_file}")
        
        with open(context_path, 'r', encoding='utf-8') as f:
            self.document_context = f.read()
        
        print(f"✓ Loaded context from: {context_file}")
        print(f"  Context size: {len(self.document_context)} characters")
        print(f"  Estimated tokens: ~{len(self.document_context.split()) * 1.3:.0f}")
        print()
    
    def load_section(self, section_file: str) -> str:
        """Load a specific section file"""
        section_path = Path(section_file)
        if not section_path.exists():
            raise FileNotFoundError(f"Section file not found: {section_file}")
        
        with open(section_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def ask(self, question: str, section_files: Optional[List[str]] = None) -> str:
        """
        Ask Claude a question about the document
        Optionally include specific section files for detailed analysis
        """
        if not self.document_context:
            raise ValueError("No context loaded. Call load_context() first.")
        
        # Build the user message
        user_content = question
        
        # Add section content if provided
        if section_files:
            sections_content = []
            for section_file in section_files:
                try:
                    section_content = self.load_section(section_file)
                    sections_content.append(f"\n\n--- Content from {section_file} ---\n\n{section_content}")
                except FileNotFoundError as e:
                    print(f"Warning: {e}")
            
            if sections_content:
                user_content += "\n\n" + "\n".join(sections_content)
        
        # Add to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": user_content
        })
        
        # Create system messages with caching
        system_messages = [
            {
                "type": "text",
                "text": self.system_prompt
            },
            {
                "type": "text",
                "text": f"DOCUMENT CONTEXT:\n\n{self.document_context}",
                "cache_control": {"type": "ephemeral"}  # Cache the context!
            }
        ]
        
        # Make API call
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=system_messages,
                messages=self.conversation_history
            )
            
            # Track token usage
            usage = response.usage
            self.total_input_tokens += usage.input_tokens
            self.total_output_tokens += usage.output_tokens
            
            # Track cache metrics
            if hasattr(usage, 'cache_creation_input_tokens'):
                self.cache_creation_tokens += usage.cache_creation_input_tokens
            if hasattr(usage, 'cache_read_input_tokens'):
                self.cache_read_tokens += usage.cache_read_input_tokens
            
            # Get response text
            assistant_message = response.content[0].text
            
            # Add to conversation history
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            return assistant_message
            
        except anthropic.APIError as e:
            print(f"API Error: {e}")
            # Remove the failed message from history
            self.conversation_history.pop()
            raise
    
    def get_usage_stats(self) -> Dict:
        """Get token usage and cost statistics"""
        # Pricing (as of 2025, check anthropic.com/pricing for current rates)
        input_price = 3.00 / 1_000_000  # $3 per million tokens
        output_price = 15.00 / 1_000_000  # $15 per million tokens
        cache_write_price = 3.75 / 1_000_000  # $3.75 per million tokens
        cache_read_price = 0.30 / 1_000_000  # $0.30 per million tokens
        
        # Calculate costs
        input_cost = self.total_input_tokens * input_price
        output_cost = self.total_output_tokens * output_price
        cache_write_cost = self.cache_creation_tokens * cache_write_price
        cache_read_cost = self.cache_read_tokens * cache_read_price
        
        total_cost = input_cost + output_cost + cache_write_cost + cache_read_cost
        
        # Calculate savings from caching
        without_cache_cost = (self.total_input_tokens + self.cache_read_tokens) * input_price + output_cost
        savings = without_cache_cost - total_cost
        
        return {
            'input_tokens': self.total_input_tokens,
            'output_tokens': self.total_output_tokens,
            'cache_creation_tokens': self.cache_creation_tokens,
            'cache_read_tokens': self.cache_read_tokens,
            'total_cost': total_cost,
            'cache_savings': savings,
            'messages_sent': len(self.conversation_history) // 2
        }
    
    def print_usage_stats(self):
        """Print formatted usage statistics"""
        stats = self.get_usage_stats()
        
        print("\n" + "="*60)
        print("TOKEN USAGE & COST STATISTICS")
        print("="*60)
        print(f"Messages sent: {stats['messages_sent']}")
        print(f"\nInput tokens: {stats['input_tokens']:,}")
        print(f"Output tokens: {stats['output_tokens']:,}")
        print(f"Cache creation tokens: {stats['cache_creation_tokens']:,}")
        print(f"Cache read tokens: {stats['cache_read_tokens']:,}")
        print(f"\nTotal cost: ${stats['total_cost']:.4f}")
        if stats['cache_savings'] > 0:
            print(f"Cache savings: ${stats['cache_savings']:.4f} ✓")
        print("="*60 + "\n")
    
    def reset_conversation(self):
        """Reset conversation history while keeping context"""
        self.conversation_history = []
        print("✓ Conversation history reset")
        print("  Note: System prompt and mode remain unchanged\n")
    
    def save_prompt_template(self, name: str, prompt: str, filepath: str = "prompt_templates.txt"):
        """Save a custom prompt template to a file"""
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"TEMPLATE: {name}\n")
            f.write(f"{'='*60}\n")
            f.write(prompt)
            f.write(f"\n{'='*60}\n\n")
        print(f"✓ Template '{name}' saved to {filepath}\n")


def interactive_mode(analyzer: ClaudePDFAnalyzer, output_dir: str):
    """Run interactive CLI for asking questions"""
    print("\n" + "="*60)
    print("INTERACTIVE PDF ANALYSIS MODE")
    print("="*60)
    print(f"\nCurrent mode: {analyzer.current_mode}")
    print("\nCommands:")
    print("  ask <question>           - Ask a question")
    print("  load <section_file>      - Load and analyze a specific section")
    print("  mode <mode_name>         - Switch analysis mode")
    print("  modes                    - List available modes")
    print("  prompt <text>            - Set custom system prompt")
    print("  show-prompt              - Show current system prompt")
    print("  save-template <name>     - Save current prompt as template")
    print("  stats                    - Show token usage statistics")
    print("  reset                    - Reset conversation history")
    print("  list                     - List available section files")
    print("  help                     - Show this help")
    print("  quit or exit             - Exit")
    print("\nTip: You can also type questions directly without 'ask' command")
    print("="*60 + "\n")
    
    output_path = Path(output_dir)
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            
            # Parse command
            parts = user_input.split(maxsplit=1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            
            # Handle commands
            if command in ['quit', 'exit', 'q']:
                analyzer.print_usage_stats()
                print("Goodbye!")
                break
            
            elif command == 'stats':
                analyzer.print_usage_stats()
            
            elif command == 'reset':
                analyzer.reset_conversation()
            
            elif command == 'mode':
                if not args:
                    print("Error: Please specify a mode\n")
                    print(f"Available modes: {', '.join(analyzer.get_available_modes())}\n")
                    continue
                
                try:
                    # Reset conversation when switching modes
                    analyzer.conversation_history = []
                    analyzer.set_mode(args)
                    print("Note: Conversation history was reset due to mode change\n")
                except ValueError as e:
                    print(f"Error: {e}\n")
            
            elif command == 'modes':
                print("\nAvailable analysis modes:")
                for mode in analyzer.get_available_modes():
                    prompt_preview = analyzer.PRESET_PROMPTS[mode].split('\n')[0][:80]
                    print(f"  - {mode}: {prompt_preview}...")
                print()
            
            elif command == 'prompt':
                if not args:
                    print("Error: Please provide a custom system prompt\n")
                    continue
                
                # Reset conversation when changing prompt
                analyzer.conversation_history = []
                analyzer.set_custom_prompt(args)
                print("Note: Conversation history was reset due to prompt change\n")
            
            elif command == 'show-prompt':
                analyzer.show_current_mode()
            
            elif command == 'save-template':
                if not args:
                    print("Error: Please provide a template name\n")
                    continue
                
                analyzer.save_prompt_template(args, analyzer.system_prompt)
            
            elif command == 'help':
                print("\nCommands:")
                print("  ask <question>           - Ask a question")
                print("  load <file>              - Load specific section")
                print("  mode <mode_name>         - Switch analysis mode")
                print("  modes                    - List available modes")
                print("  prompt <text>            - Set custom prompt")
                print("  show-prompt              - Show current prompt")
                print("  save-template <name>     - Save prompt template")
                print("  stats                    - Show usage statistics")
                print("  reset                    - Reset conversation")
                print("  list                     - List section files")
                print("  quit/exit                - Exit\n")
            
            elif command == 'list':
                section_files = sorted(output_path.glob("*.txt"))
                print("\nAvailable section files:")
                for f in section_files:
                    print(f"  - {f.name}")
                print()
            
            elif command == 'load':
                if not args:
                    print("Error: Please specify a section file\n")
                    continue
                
                section_path = output_path / args
                if not section_path.exists():
                    # Try with just the filename
                    section_path = output_path / Path(args).name
                
                question = f"Please analyze this section in detail:\n\n"
                print("\nClaude: ", end="", flush=True)
                response = analyzer.ask(question, [str(section_path)])
                print(response + "\n")
            
            elif command == 'ask':
                if not args:
                    print("Error: Please provide a question\n")
                    continue
                
                print("\nClaude: ", end="", flush=True)
                response = analyzer.ask(args)
                print(response + "\n")
            
            else:
                # Treat as direct question
                print("\nClaude: ", end="", flush=True)
                response = analyzer.ask(user_input)
                print(response + "\n")
        
        except KeyboardInterrupt:
            print("\n\nInterrupted. Use 'quit' to exit.\n")
        except Exception as e:
            print(f"\nError: {e}\n")


def main():
    """Main execution"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Analyze PDF sections using Claude with prompt caching"
    )
    parser.add_argument(
        "context_file",
        help="Path to document context file (e.g., 00_CLAUDE_CONTEXT.md)"
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory containing section files (default: output)"
    )
    parser.add_argument(
        "--api-key",
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)"
    )
    parser.add_argument(
        "--mode",
        "-m",
        default="generic",
        choices=['generic', 'research', 'legal', 'business', 'technical', 'medical'],
        help="Analysis mode preset (default: generic)"
    )
    parser.add_argument(
        "--system-prompt",
        help="Custom system prompt (overrides --mode)"
    )
    parser.add_argument(
        "--list-modes",
        action="store_true",
        help="List all available analysis modes and exit"
    )
    parser.add_argument(
        "--question",
        "-q",
        help="Ask a single question and exit (non-interactive mode)"
    )
    parser.add_argument(
        "--sections",
        "-s",
        nargs="+",
        help="Section files to include with question"
    )
    
    args = parser.parse_args()
    
    # List modes and exit
    if args.list_modes:
        print("\nAvailable Analysis Modes:\n")
        temp_analyzer = ClaudePDFAnalyzer(api_key="dummy")
        for mode in temp_analyzer.get_available_modes():
            prompt = temp_analyzer.PRESET_PROMPTS[mode]
            print(f"{mode.upper()}:")
            print(f"  {prompt[:150]}...")
            print()
        sys.exit(0)
    
    try:
        # Initialize analyzer with mode or custom prompt
        if args.system_prompt:
            analyzer = ClaudePDFAnalyzer(api_key=args.api_key, custom_prompt=args.system_prompt)
        else:
            analyzer = ClaudePDFAnalyzer(api_key=args.api_key, mode=args.mode)
        
        # Load context
        analyzer.load_context(args.context_file)
        
        # Non-interactive mode
        if args.question:
            print(f"Question: {args.question}\n")
            response = analyzer.ask(args.question, args.sections)
            print(f"Claude: {response}\n")
            analyzer.print_usage_stats()
        else:
            # Interactive mode
            interactive_mode(analyzer, args.output_dir)
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()


