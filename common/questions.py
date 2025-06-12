#! /usr/bin/env python3

import json
import random
import sys
import os
from time import sleep
from pygments import highlight
from pygments.lexers import CLexer
from pygments.formatters import TerminalFormatter
# JSON format of questions file
"""
[
    {
        "question": "The question",
        "code": "a code example if needed, do not include code in question iteself",
        "correct_answer": "the correct answer text",
        "possible_responses": ["optional", "list", "of responses", "that will", "be presented", "to the user", "as a mly ordered", "multiple choice"],
        "comment": "Describes what the question is assessing",
        "positive_response": "gives a positive response and feedback on why",
        "negative_response": "gives a negative response and feedback on the purpose of the question and what to think about before making the next attempt"
    },
    ...
]
"""


def find_question_file():
    # Get the directory where the Python script is located
    script_directory = "/challenge"  if os.path.exists("/challenge") else os.getcwd()

    # List all files in that directory
    files_in_directory = os.listdir(script_directory)

    # Iterate through the files
    for filename in files_in_directory:
        if "question" in filename and filename.endswith("json"):
            return os.path.join(script_directory, filename)
    return None


def get_random_letter(used_letters):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    available = [l for l in alphabet if l not in used_letters]
    if not available:
        raise ValueError("Too many possible responses for a single question!")
    return random.choice(available)


def display_question(question_dict):
    print(question_dict["question"])

    # Highlight and display the C code
    if "code" in question_dict and question_dict["code"].strip():
        code = question_dict["code"]
        highlighted_code = highlight(code, CLexer(), TerminalFormatter())
        print(highlighted_code)

    response_mapping = {}
    used_letters = []

    if "possible_responses" in question_dict:
        for response in question_dict["possible_responses"]:
            letter = get_random_letter(used_letters)
            used_letters.append(letter)
            response_mapping[letter] = response

        # Sort by letter and display
        for letter, response in sorted(response_mapping.items()):
            print(f"{letter}. {response}")

    return response_mapping


def main():
    # Use find_qqq_file function to get the path to the JSON file
    json_file_path = find_question_file()

    if not json_file_path:
        print("Could not find a file with 'QQQ' in its name.")
        return

    # Read from the found JSON file
    with open(json_file_path, "r") as file:
        questions = json.load(file)


    for question in questions:
        missed_last_question = True
        while missed_last_question:
            response_mapping = display_question(question)
            user_response = input("Enter your answer: ").strip().upper()
            # Check if there are possible responses
            if response_mapping and "possible_responses" in question and len(question["possible_responses"]) > 1:
                if user_response not in response_mapping:
                    print("\033[91mInvalid input...Did you pick a letter from the choices? \033[0m")
                    missed_last_question = True
                    sleep(3)
                    continue
                user_response = response_mapping[user_response]

            if user_response == question["correct_answer"]:
                missed_last_question = False
                positive = question.get('positive_response', "Correct!")
                print(f"\033[92m{positive}\033[0m")  # ANSI for green text
                sleep(2)
            else:
                missed_last_question = True
                negative = question.get('negative_response', "Incorrect answer.")
                print(f"\033[91m{negative}. \033[0m")  # ANSI for red text
                sleep(5)
            print("\n")



    print("\033[92mCongratulations, all questions answered correctly!\033[0m")


if __name__ == "__main__":
    main()
