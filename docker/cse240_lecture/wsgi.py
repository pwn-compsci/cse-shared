#!/usr/bin/env python
#ERIK 4
import gzip
import json
import os
import time
from pathlib import Path
import random 

from flask import Flask, redirect, render_template, request
import hashlib


app = Flask(__name__)

flag = open("/flag").read().strip()

with open ("/challenge/.config/level.json", "r") as af:
    if not af.readable():
        raise RuntimeError("Cannot read level.json file")
    level_json = json.load(af)
    YOUTUBE_ID = level_json.get("youtube_id")
    TOTAL_TIME = level_json.get("total_time")
    mcq_question_pool = level_json.get("mcq_question_pool", [])
    mcq = random.choice(mcq_question_pool) if mcq_question_pool else {}
    mcq_question = mcq.get("question", "")
    mcq_options = mcq.get("options", [])
    if len(mcq_options) > 0:
        mcq_options = random.sample(mcq_options, len(mcq_options))
    max_mcq_attempts = mcq.get("max_attempts", 2)

correct_value = next((opt["value"] for opt in mcq_options if opt.get("correct")), None)
mcq_correct = hashlib.sha256(correct_value.encode()).hexdigest() if correct_value else ""
lecture_context = {
    'youtube_id': YOUTUBE_ID,
    "mcq_question": mcq_question,
    "mcq_options": mcq_options,
    "mcq_correct": mcq_correct
}
answer_attempts = 0

# Read the level configuration
#YOUTUBE_ID, TOTAL_TIME = open("/challenge/.config/level.json").read().strip().split()
TOTAL_TIME = int(TOTAL_TIME)


def open_timeline_file():
    local_share_dir = Path("/home/hacker/.local/share/")
    local_share_dir.mkdir(parents=True, exist_ok=True)
    os.chown(local_share_dir, 1000, 1000)
    timeline_path = local_share_dir / "lectures" / f"{YOUTUBE_ID}.gz"
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    existing_data = []
    try:
        for line in gzip.open(timeline_path, "rb"):
            existing_data.append(line)
    except (FileNotFoundError, EOFError):
        pass
    timeline_file = gzip.open(timeline_path, "wb")
    if existing_data:
        timeline_file.writelines(existing_data)
        timeline_file.flush()
    return timeline_file

def reset_timeline_file():
    local_share_dir = Path("/home/hacker/.local/share/")
    timeline_path = local_share_dir / "lectures" / f"{YOUTUBE_ID}.gz"
    if timeline_path.exists():
        timeline_path.unlink()
    return open_timeline_file()    
    

timeline = []
timeline_file = open_timeline_file()


@app.route("/")
def index():
    return redirect(f"{YOUTUBE_ID}/")


@app.route("/<youtube_id>/") 
def lecture(youtube_id): 
            
    return render_template("lecture.html", **lecture_context)

@app.route("/<youtube_id>/telemetry_reset", methods=["GET", "POST"]) 
def reset_telemetry(youtube_id):
    global timeline_file, timeline
    timeline_file.close()
    timeline = []
    timeline_file = reset_timeline_file()
    print(f"Telemetry reset for {youtube_id}")
    return {"status": "success", "message": "Telemetry reset successfully"} 

@app.route("/<youtube_id>/telemetry", methods=["GET", "POST"])
def update_telemetry(youtube_id): 
    if youtube_id != YOUTUBE_ID:
        return {"error": "Incorrect video"}, 400  

    fields = {
        "reason": str,
        "player": ["state", "time", "muted", "volume", "rate", "loaded", "duration", "url"],
        "document": ["visibility", "fullscreen", "agent"],
    }
    for field in fields:
        if field not in request.json:
            return {"error": f"Missing required data"}, 400
        if isinstance(fields[field], list):
            for sub_field in fields[field]:
                if sub_field not in request.json[field]:
                    return {"error": f"Missing required data"}, 400
    event = request.json.copy() 
    event["youtube_id"] = youtube_id
    event["timestamp"] = time.time()
    timeline.append(event)
    timeline_file.write(json.dumps(event).encode() + b"\n")
    timeline_file.flush()

    result = {}

    valid_coverage, invalid_coverage = resolve_timeline_coverage(timeline)
    result["coverage"] = {"valid": valid_coverage, "invalid": invalid_coverage}
    total_valid_time = sum(end - start for start, end in valid_coverage)
    completed = total_valid_time > TOTAL_TIME - 5
    print(f"{completed=}")
    result["completed"] = completed
    result["youtube_id"] = youtube_id
    result["total_valid_time"] = total_valid_time
    if completed and len(mcq_correct) < 3:
        result["flag"] = flag

    return result

@app.route("/<youtube_id>/knowledge_check", methods=["GET", "POST"]) 
def knowledge_check(youtube_id):
    global answer_attempts
    input = request.json
    answer_value = input.get('answer_value',"")
    answer_attempts += 1
    if len(answer_value) > 0:
        if answer_value == next((opt["value"] for opt in mcq_options if opt.get("correct")), None): 
            return {"status": "correct", "flag": flag}
        else:
            incorrect_return = {"status": "incorrect", 
                                "message": "Incorrect. Too many incorrect responses will result in you having to re-watch the video.", 
                                "answer_attempts": answer_attempts, "max_mcq_attempts": max_mcq_attempts}            
            if answer_attempts == max_mcq_attempts:
                reset_telemetry(youtube_id)
                incorrect_return["message"] = "Incorrect. You have reached the maximum number of attempts. Please re-watch the video."
                
            elif answer_attempts == (max_mcq_attempts-1):
                incorrect_return["message"] = "Incorrect. Next incorrect response will require you to re-watch the video."

            return incorrect_return 
        
def resolve_timeline_coverage(timeline):
    if not timeline:
        return

    valid_coverage = []
    invalid_coverage = []

    last_time = timeline[0]["player"]["time"]
    last_timestamp = timeline[0]["timestamp"]

    for event in timeline[1:]:
        elapsed_time = event["player"]["time"] - last_time
        elapsed_timestamp = event["timestamp"] - last_timestamp

        if elapsed_timestamp * 2 + 2 > elapsed_time > 0:
            valid_coverage.append((last_time, event["player"]["time"]))
        elif elapsed_time > 0:
            invalid_coverage.append((last_time, event["player"]["time"]))

        last_time = event["player"]["time"]
        last_timestamp = event["timestamp"]

    def merge_intervals(intervals):
        if not intervals:
            return []
        intervals = sorted(intervals, key=lambda x: x[0])
        merged = [intervals[0]]
        for current_start, current_end in intervals[1:]:
            last_start, last_end = merged[-1]
            if current_start <= last_end:
                merged[-1] = (last_start, max(last_end, current_end))
            else:
                merged.append((current_start, current_end))
        return merged

    valid_coverage = merge_intervals(valid_coverage)
    invalid_coverage = merge_intervals(invalid_coverage)

    def subtract_intervals(intervals, subtracting):
        result = []
        for (int_start, int_end) in intervals:
            current_start = int_start
            for (sub_start, sub_end) in subtracting:
                if sub_end <= current_start or sub_start >= int_end:
                    continue
                if sub_start > current_start:
                    result.append((current_start, sub_start))
                current_start = max(current_start, sub_end)
                if current_start >= int_end:
                    break
            if current_start < int_end:
                result.append((current_start, int_end))
        return result

    invalid_coverage = subtract_intervals(invalid_coverage, valid_coverage)

    return valid_coverage, invalid_coverage

application = app