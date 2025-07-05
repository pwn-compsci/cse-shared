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
import logging

app = Flask(__name__)

# Configure logging to propagate to Gunicorn's logger
log = logging.getLogger('gunicorn.error')
log_file_path = "/var/log/gunicorn/logger.log"
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
log.addHandler(file_handler)
log.setLevel(logging.INFO)

if log.handlers:
    app.logger.handlers = log.handlers
    app.logger.setLevel(log.level)
else:
    logging.basicConfig(level=logging.INFO)

flag = open("/flag").read().strip()

with open ("/challenge/.config/level.json", "r") as af:
    if not af.readable():
        raise RuntimeError("Cannot read level.json file")
    level_json = json.load(af)
    YOUTUBE_ID = level_json.get("youtube_id")
    IFRAME_URL = level_json.get("iframe_url", f"")
    TOTAL_TIME = level_json.get("total_time", 30)
    if isinstance(TOTAL_TIME, str) and len(TOTAL_TIME) == 0:
        TOTAL_TIME = 30 # Default to 30 seconds if not specified or invalid
        
    mcq_question_pool = level_json.get("mcq_question_pool", [])
    mcq_to_ask = min(level_json.get("mcq_to_ask", 1), len(mcq_question_pool))
    
    if level_json.get("randomize_order", True):
        mcqs = random.sample(mcq_question_pool, mcq_to_ask) if mcq_question_pool else []
    else:
        mcqs = mcq_question_pool[:mcq_to_ask] if mcq_question_pool else []
    for mcqid, mcq in enumerate(mcqs):
        mcq["id"] = f"question_{mcqid}"
        if "options" in mcq and mcq["options"]:
            mcq["options"] = random.sample(mcq["options"], len(mcq["options"]))
    max_mcq_attempts = level_json.get("max_attempts", 2)
    log.info(f"{mcq_to_ask=}, {len(mcq_question_pool)=}. {level_json.get('mcq_to_ask', 1)=} {max_mcq_attempts=}")
    log.info(f"Loaded {json.dumps(mcqs,indent=2)} MCQs to ask from the pool.")
lecture_context = {
    'youtube_id': YOUTUBE_ID,
    'iframe_url': IFRAME_URL,
    "mcqs": mcqs
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
    global timeline_file, timeline, answer_attempts
    answer_attempts = 0
    timeline_file.close()
    timeline = []
    timeline_file = reset_timeline_file()
    print(f"Telemetry reset for {youtube_id}")
    return {"status": "success", "message": "Telemetry reset successfully"} 

@app.route("/<youtube_id>/telemetry", methods=["GET", "POST"])
def update_telemetry(youtube_id): 
    global answer_attempts
    
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
    
    if event["player"]["state"] == 0: # 0 means player ended
        answer_attempts = 0

    timeline.append(event)
    timeline_file.write(json.dumps(event).encode() + b"\n")
    timeline_file.flush()

    result = {}

    valid_coverage, invalid_coverage = resolve_timeline_coverage(timeline)
    result["coverage"] = {"valid": valid_coverage, "invalid": invalid_coverage}
    total_valid_time = sum(end - start for start, end in valid_coverage)
    completed = total_valid_time > (TOTAL_TIME - 15) # 15 seconds tolerance
    
    log.info(f"{event['userId']}, {type(event['userId'])} {event['userId'] == 97168},  {event['userId'] == '97168'} completed={completed} total_valid_time={total_valid_time}")
    if event["userId"] == 97168:
        completed = True # force completion for user 97168

    print(f"{completed=}")
    result["completed"] = completed

    result["youtube_id"] = youtube_id
    result["total_valid_time"] = total_valid_time
    if completed and len(mcqs) < 1:
        result["flag"] = flag

    return result

@app.route("/<youtube_id>/knowledge_check", methods=["GET", "POST"]) 
def knowledge_check(youtube_id):
    global answer_attempts
    input = request.json
    question_eval = {} 
    all_questions_correct = True 
    # responses = [{"question_id": "question_0", "answer": "correct_option"}]
    responses = input.get("responses", [])
    if not isinstance(responses, list):
        print(f"Received responses: {responses}")
        return {"error": "Invalid response format"}, 400
    
    if len(responses) == 0:
        return {"error": f"No responses found. "}, 400
    
    if youtube_id != YOUTUBE_ID:
        if len(IFRAME_URL) < 5:
            return {"error": "Incorrect video"}, 400
    
    # Do the responses contain all the question IDs?
    response_ids = {resp["question_id"] for resp in responses if isinstance(resp, dict) and "question_id" in resp}
    mcq_ids = {mcq["id"] for mcq in mcqs}
    if not mcq_ids.issubset(response_ids):
        for missing_id in mcq_ids - response_ids:
            question_eval[missing_id] = {"status": "incorrect", "message": "No answer provided."}
        all_questions_correct = False 
    
    # test whether the response is correct
    for resp in responses:
        if not isinstance(resp, dict) or "question_id" not in resp:
            return {"error": f"Invalid response format, nice try. dict={not isinstance(resp, dict)} or question_id = {'question_id' not in resp} {resp}"}, 400
        elif "answer" not in resp:
            question_eval[resp["question_id"]] = {"status": "malformed", "message": "The response is malformed. Nice try."}
            all_questions_correct = False 
        
        stored_mcq = next((mcq for mcq in mcqs if mcq["id"] == resp["question_id"]), None)            
        stored_mcq_answer = next((opt["value"] for opt in stored_mcq.get("options", []) if opt.get("correct")), None)
        log.info(f"Checking response: {resp['question_id']} with answer {resp['answer']} against stored answer {stored_mcq_answer}")
        if resp["answer"] == stored_mcq_answer:
            question_eval[resp["question_id"]] = {"status": "correct", "message": "Correct answer."}
            all_questions_correct = True and all_questions_correct # only if all questions are correct
        else:
            question_eval[resp["question_id"]] = {"status": "incorrect", "message": "Incorrect answer."}
            all_questions_correct = False
    
    answer_attempts += 1
    return_value = {"status": "incorrect", 
                        "message": "Incorrect. Too many incorrect responses will result in you having to re-watch the video.", 
                        "answer_attempts": answer_attempts, "max_mcq_attempts": max_mcq_attempts,
                        "question_eval": question_eval}            
    log.info(f"Answer attempts: {answer_attempts}, max attempts: {max_mcq_attempts}, all questions correct: {all_questions_correct}")
    if all_questions_correct:    
        if answer_attempts > max_mcq_attempts:
            reset_telemetry(youtube_id)
            #return {"status": "incorrect", "message": "You have reached the maximum number of attempts. Please re-watch the video."}
            return_value["message"] = "Incorrect. You have reached the maximum number of attempts. Please re-watch the video."
            return return_value                
        return {"status": "correct", "flag": flag}
    else:            
        if answer_attempts >= max_mcq_attempts:
            reset_telemetry(youtube_id)
            return_value["message"] = "Incorrect. You have reached the maximum number of attempts. Please re-watch the video."                    
        elif answer_attempts == (max_mcq_attempts-1):
            return_value["message"] = "Incorrect. Next incorrect response will require you to re-watch the video."
        return return_value 
    
        
    
        
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