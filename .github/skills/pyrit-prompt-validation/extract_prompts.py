#!/usr/bin/env python3
"""
Extract AI system prompts from source code files.

This utility scans source files (Python, C#, JavaScript/TypeScript) for AI system
prompts and outputs them in JSON format for inspection, validation, or analysis.

Supported Formats:
  - C#: CreateAIAgent(..., instructions: \"\"\"...\"\"\")
  - Python: system_prompt = \"\"\"...\"\"\"
  - JavaScript/TypeScript: systemMessage: \"...\"

Usage:
    # Extract from single file
    python extract_prompts.py --file src/MyAgent.cs
    
    # Extract from directory (recursive)
    python extract_prompts.py --source-dir src --pattern "*Agent*.cs"
    
    # Include code context (for verification)
    python extract_prompts.py --source-dir src --include-context
    
    # Output to file
    python extract_prompts.py --source-dir src --output prompts.json

Exit Codes:
    0 - Success (prompts extracted successfully)
    1 - Error during extraction (file not found, parse error, etc.)

Examples:
    >>> extractor = PromptExtractor()
    >>> prompts = extractor.extract_from_file("src/MyAgent.cs")
    >>> print(f"Total: {len(prompts)} prompts")
    Total: 2 prompts
    
    >>> prompts = extractor.extract_from_directory("src", pattern="*Agent*.cs")
    >>> print(f"Total: {len(prompts)} prompts")
    Total: 5 prompts

References:
    - PEP 257: Docstring Conventions
    - PEP 484: Type Hints
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Union
import re


class PromptExtractor:
    """
    Extract AI prompts from various source file formats.
    
    This class provides static methods to scan source code files for AI system
    prompts in multiple programming languages and formats. It uses regex patterns
    to identify and extract prompt text along with metadata like file location,
    line numbers, and optional code context.
    
    Supported Languages:
        - C# (.cs): CreateAIAgent pattern with instructions parameter
        - Python (.py): Variable assignments to system_prompt, instructions, meta_prompt
        - JavaScript/TypeScript (.js, .ts, .jsx, .tsx): Object properties with prompts
    
    Attributes:
        CSHARP_AGENT_PATTERN: Regex for C# CreateAIAgent calls with instructions
        PYTHON_PROMPT_PATTERN: Regex for Python prompt variable assignments
        JS_PROMPT_PATTERN: Regex for JavaScript/TypeScript prompt properties
    """

    CSHARP_AGENT_PATTERN = re.compile(
        r'\.CreateAIAgent\s*\(\s*.*?instructions:\s*"""(.*?)"""',
        re.DOTALL | re.MULTILINE,
    )

    PYTHON_PROMPT_PATTERN = re.compile(
        r'(?:system_prompt|instructions|meta_prompt)\s*=\s*[f]?"""(.*?)"""',
        re.DOTALL | re.MULTILINE,
    )

    JS_PROMPT_PATTERN = re.compile(
        r'(?:systemMessage|instructions|metaPrompt):\s*[`"\'](.*?)[`"\']',
        re.DOTALL | re.MULTILINE,
    )

    @staticmethod
    def extract_from_file(file_path: str, include_context: bool = False) -> List[Dict[str, Union[str, int]]]:
        """
        Extract all prompts from a single source file.
        
        Scans the specified file for AI system prompts based on the file's
        extension and programming language. Extracts prompt text along with
        metadata including location, line number, and optionally surrounding
        code context.
        
        Args:
            file_path: Path to source file to scan (C#, Python, JS/TS)
            include_context: If True, includes surrounding code lines (±3 lines before,
                           +10 lines after) for verification. Default is False.
        
        Returns:
            List of dictionaries, each containing:
                - id (str): Agent/prompt identifier (e.g., "MyAgent" or "PythonPrompt_1")
                - file (str): Path to the source file
                - language (str): Source language ("csharp", "python", "javascript")
                - text (str): Extracted prompt text content
                - line (int): Line number where prompt starts (1-indexed)
                - length (int): Character length of the prompt text
                - context (str, optional): Surrounding code if include_context=True
        
        Raises:
            FileNotFoundError: If the specified file does not exist
            IOError: If the file cannot be read (permissions, encoding issues)
            
        Examples:
            >>> prompts = PromptExtractor.extract_from_file("src/MyService.cs")
            >>> print(f"Found {len(prompts)} prompts")
            Found 2 prompts
            
            >>> prompts = PromptExtractor.extract_from_file(
            ...     "src/MyService.cs",
            ...     include_context=True
            ... )
            >>> print(prompts[0].keys())
            dict_keys(['id', 'file', 'language', 'text', 'line', 'length', 'context'])
        
        Note:
            Empty files or files with no matching prompts return an empty list.
            Parse errors are logged to stderr but do not raise exceptions.
        """
        prompts: List[Dict[str, Union[str, int]]] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            file_ext = Path(file_path).suffix.lower()

            if file_ext == ".cs":
                matches = PromptExtractor.CSHARP_AGENT_PATTERN.finditer(content)
                for match in matches:
                    prompt_text = match.group(1).strip()
                    name_match = re.search(r'name:\s*"([^"]+)"', match.group(0))
                    agent_name = name_match.group(1) if name_match else "UnnamedAgent"

                    line_num = content[: match.start()].count("\n") + 1

                    prompt_data: Dict[str, Union[str, int]] = {
                        "id": agent_name,
                        "file": file_path,
                        "language": "csharp",
                        "text": prompt_text,
                        "line": line_num,
                        "length": len(prompt_text),
                    }

                    if include_context:
                        lines = content.split("\n")
                        start_line = max(0, line_num - 3)
                        end_line = min(len(lines), line_num + 10)
                        prompt_data["context"] = "\n".join(lines[start_line:end_line])

                    prompts.append(prompt_data)

            elif file_ext == ".py":
                matches = PromptExtractor.PYTHON_PROMPT_PATTERN.finditer(content)
                for idx, match in enumerate(matches):
                    line_num = content[: match.start()].count("\n") + 1
                    text = match.group(1).strip()
                    prompts.append(
                        {
                            "id": f"PythonPrompt_{idx + 1}",
                            "file": file_path,
                            "language": "python",
                            "text": text,
                            "line": line_num,
                            "length": len(text),
                        }
                    )

            elif file_ext in [".js", ".ts", ".jsx", ".tsx"]:
                matches = PromptExtractor.JS_PROMPT_PATTERN.finditer(content)
                for idx, match in enumerate(matches):
                    line_num = content[: match.start()].count("\n") + 1
                    text = match.group(1).strip()
                    prompts.append(
                        {
                            "id": f"JSPrompt_{idx + 1}",
                            "file": file_path,
                            "language": "javascript",
                            "text": text,
                            "line": line_num,
                            "length": len(text),
                        }
                    )

        except Exception as e:
            print(f"Error extracting from {file_path}: {e}", file=sys.stderr)

        return prompts

    @staticmethod
    def extract_from_directory(directory: str, pattern: str = "*") -> List[Dict[str, Union[str, int]]]:
        """
        Extract prompts from all matching files in a directory (recursive).
        
        Recursively scans the specified directory for source files matching
        the given pattern and extracts all prompts found. Searches for files
        with extensions: .cs, .py, .js, .ts, .jsx, .tsx
        
        Args:
            directory: Root directory to scan recursively for source files
            pattern: File pattern to match (glob pattern, e.g., "*Agent*.cs").
                    Default "*" matches all files with supported extensions.
        
        Returns:
            List of all prompts found across all matching files. Each prompt
            is a dictionary with the same structure as extract_from_file().
            Context is not included (set to False for performance).
        
        Raises:
            ValueError: If directory path doesn't exist or is not a directory
            
        Examples:
            >>> prompts = PromptExtractor.extract_from_directory("src")
            >>> print(f"Total: {len(prompts)} prompts")
            Total: 15 prompts
            
            >>> prompts = PromptExtractor.extract_from_directory(
            ...     "src",
            ...     pattern="*Agent*.cs"
            ... )
            >>> print(f"Total: {len(prompts)} prompts")
            Total: 5 prompts
        
        Note:
            This method does not include code context to improve performance
            when scanning large directories. To add context, extract it in
            a separate pass using extract_from_file() with include_context=True.
        """
        all_prompts: List[Dict[str, Union[str, int]]] = []
        path = Path(directory)

        extensions = ["*.cs", "*.py", "*.js", "*.ts", "*.jsx", "*.tsx"]

        for ext in extensions:
            for file_path in path.rglob(ext):
                if pattern != "*" and not file_path.match(pattern):
                    continue

                file_prompts = PromptExtractor.extract_from_file(str(file_path), include_context=False)
                all_prompts.extend(file_prompts)

        return all_prompts


def main() -> int:
    """
    Command-line interface for extracting prompts from source code.
    
    Parses command-line arguments and orchestrates prompt extraction from
    either a single file or directory of files. Outputs results as JSON
    to stdout or a specified file.
    
    Returns:
        int: Exit code (0 for success, 1 for error)
        
    Exit Codes:
        0 - Successful extraction
        1 - Error during extraction (file not found, parse error, etc.)
    """
    parser = argparse.ArgumentParser(description='Extract AI prompts from source code')

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--file', type=str, help='Single file to extract from')
    input_group.add_argument('--source-dir', type=str, help='Directory to scan')

    parser.add_argument('--pattern', type=str, default='*', help='File pattern (e.g., "*Agent*.cs")')
    parser.add_argument('--output', type=str, help='Output JSON file (default: stdout)')
    parser.add_argument('--include-context', action='store_true', help='Include code context')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    prompts = []

    if args.file:
        if args.verbose:
            print(f"Extracting from file: {args.file}", file=sys.stderr)
        prompts = PromptExtractor.extract_from_file(args.file, args.include_context)

    elif args.source_dir:
        if args.verbose:
            print(f"Scanning directory: {args.source_dir}", file=sys.stderr)

        # Use shared directory extraction and then optionally re-add context
        prompts = PromptExtractor.extract_from_directory(args.source_dir, args.pattern)

        if args.include_context:
            enriched: List[Dict[str, Union[str, int]]] = []
            for prompt in prompts:
                file_path = prompt.get("file")
                line_num = prompt.get("line")
                if not file_path or not isinstance(line_num, int):
                    enriched.append(prompt)
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.read().split("\n")
                    start_line = max(0, line_num - 3)
                    end_line = min(len(lines), line_num + 10)
                    prompt["context"] = "\n".join(lines[start_line:end_line])
                except Exception as e:
                    print(f"Error adding context for {file_path}: {e}", file=sys.stderr)

                enriched.append(prompt)

            prompts = enriched

    # Output results
    result = {
        'total_prompts': len(prompts),
        'prompts': prompts
    }

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        if args.verbose:
            print(f"\nExtracted {len(prompts)} prompts to {args.output}", file=sys.stderr)
    else:
        print(json.dumps(result, indent=2))

    return 0


if __name__ == '__main__':
    sys.exit(main())
