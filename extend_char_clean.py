#!/usr/bin/env python3
"""
Script to check files in randfiles directory for non-standard UTF-8 characters
like em-dash, fancy quotes, accented characters, etc.
"""

import os
import sys
from pathlib import Path

def is_standard_ascii(char):
    """Check if character is standard ASCII (letters, numbers, basic punctuation, whitespace)"""
    # Standard ASCII printable characters (32-126) plus common whitespace
    if ord(char) <= 127:
        # Allow letters, numbers, basic punctuation, space, tab, newline
        if char.isalnum() or char in ' \t\n\r!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~':
            return True
    return False

def find_non_standard_chars(filepath):
    """Find non-standard UTF-8 characters in a file"""
    issues = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                for char_pos, char in enumerate(line, 1):
                    if not is_standard_ascii(char):
                        issues.append({
                            'line': line_num,
                            'column': char_pos,
                            'char': char,
                            'unicode_name': char.encode('unicode_escape').decode('ascii'),
                            'code_point': ord(char),
                            'hex': f"U+{ord(char):04X}"
                        })
    except UnicodeDecodeError as e:
        issues.append({
            'line': 'N/A',
            'column': 'N/A', 
            'char': 'DECODE_ERROR',
            'unicode_name': str(e),
            'code_point': 'N/A',
            'hex': 'N/A'
        })
    except Exception as e:
        issues.append({
            'line': 'N/A',
            'column': 'N/A',
            'char': 'FILE_ERROR', 
            'unicode_name': str(e),
            'code_point': 'N/A',
            'hex': 'N/A'
        })
    
    return issues

def main():
    # Default to current directory if no argument provided
    if len(sys.argv) > 1:
        randfiles_dir = sys.argv[1]
    else:
        randfiles_dir = '/cse/cse-shared/common/randfiles'
    
    if not os.path.exists(randfiles_dir):
        print(f"Error: Directory {randfiles_dir} does not exist")
        sys.exit(1)
    
    print(f"Checking files in: {randfiles_dir}")
    print("=" * 60)
    
    total_files = 0
    files_with_issues = 0
    total_issues = 0
    
    # Walk through all files in the directory
    for root, dirs, files in os.walk(randfiles_dir):
        for filename in files:
            filepath = os.path.join(root, filename)
            relative_path = os.path.relpath(filepath, randfiles_dir)
            
            total_files += 1
            issues = find_non_standard_chars(filepath)
            
            if issues:
                files_with_issues += 1
                total_issues += len(issues)
                
                print(f"\n📁 {relative_path}")
                print("-" * 40)
                
                for issue in issues:
                    if issue['char'] == 'DECODE_ERROR':
                        print(f"  ❌ DECODE ERROR: {issue['unicode_name']}")
                    elif issue['char'] == 'FILE_ERROR':
                        print(f"  ❌ FILE ERROR: {issue['unicode_name']}")
                    else:
                        print(f"  ⚠️  Line {issue['line']}, Col {issue['column']}: "
                              f"'{issue['char']}' ({issue['hex']}) - {issue['unicode_name']}")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(f"Total files checked: {total_files}")
    print(f"Files with non-standard characters: {files_with_issues}")
    print(f"Total non-standard characters found: {total_issues}")
    
    if total_issues == 0:
        print("✅ All files contain only standard ASCII characters!")
    else:
        print("⚠️  Some files contain non-standard UTF-8 characters")
        print("\nCommon non-standard characters to look for:")
        print("  • Em-dash (—) vs hyphen (-)")
        print("  • En-dash (–) vs hyphen (-)")
        print("  • Curly quotes (" ") vs straight quotes (\" \")")
        print("  • Single curly quotes (' ') vs straight quotes (' ')")
        print("  • Ellipsis (…) vs three periods (...)")
        print("  • Accented characters (é, ñ, ü, etc.)")

if __name__ == "__main__":
    main()