from flask import Flask, request, Response, session, render_template_string, redirect, make_response, render_template
from datetime import datetime, timedelta
from datetime import timezone
from time import sleep 
from hashlib import sha256
import re 
import requests
import subprocess
import os
import logging
import json
import html
import csv

# Setup logger
logger = logging.getLogger('gevent.server')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
logger.addHandler(handler)

app = Flask(__name__)
app.secret_key = 'donnowhatyouthinkyouwant'

# SHAPASS_VALUE is replaced with the actual sha value, which will match nginx's LETMEIN
shapass = "SHAPASS_VALUE"

pwn_college_id = "" # initialized at bottom in default script area
CODESERVER_TRACK_FILE = "/challenge/started.dat"
NGINX_CONF_FILE = "/challenge/web/nginx.conf"
FLAG_EXEMPTED_PATH = "/flag_exempted"

# Exam administration type configuration
exam_admin_type = "Proctoring plus Lockdown Browser"  # Default to most restrictive
exam_module = ""
exam_challenge = ""
exam_admin_type_lookup_error = ""
EXAM_ADMIN_API_TOKEN = "08b26e01b8d9cb4f262da37836912504104296c33ab658dca836d032bc47b2ff"
EXAM_ADMIN_API_URL = "https://api.cse545.com/exam_admin_type"
EXAM_GATE_STATUS_API_URL = "https://api.cse545.com/exam-gates/checkstatus"
last_session_attendance_error = ""
last_session_student_name = ""

def normalized_exam_admin_type(value=None):
    return (exam_admin_type if value is None else value or "").strip().lower().replace("_", " ").replace("-", " ")

def is_proctoring_only(value=None):
    exam_type = normalized_exam_admin_type(value)
    return exam_type in {
        "proctoring",
        "proctor only",
        "proctoring only",
    }

def is_honorlock_exam(value=None):
    return normalized_exam_admin_type(value).replace(" ", "") == "honorlock"

def is_lockdown_browser_exam(value=None):
    exam_type = normalized_exam_admin_type(value)
    return exam_type in {
        "lock down browser",
        "lockdown browser",
    }

def requires_active_proctor_session(value=None):
    exam_type = normalized_exam_admin_type(value)
    return is_proctoring_only(value) or exam_type in {
        "proctoring plus lockdown browser",
        "proctoring with no attendance",
    }

def requires_attendance_monitoring(value=None):
    exam_type = normalized_exam_admin_type(value)
    return is_proctoring_only(value) or exam_type in {
        "proctoring plus lockdown browser",
    }

def requires_exam_password(value=None):
    exam_type = normalized_exam_admin_type(value)
    return exam_type in {
        "proctoring plus lockdown browser",
        "lock down browser",
    }

def has_exam_admin_type_lookup_error():
    return bool(exam_admin_type_lookup_error)

def is_admin_bypass_user(pwn_college_id):
    try:
        return int(pwn_college_id) in BYPASS_RLDB_IDS if pwn_college_id else False
    except (ValueError, TypeError):
        return False

# Hardcoded set of pwn_college_id values that skip RLDB check
#, 97169 
# 68880 is Weiyu admin account
# 42906 is Derek admin account
# 97168 Erik 1 
# 129911 Vishal
# 64397 sri
# 109275 madu
# 68429 vmamshi
# 44674 gio
# 157464 omy1 
BYPASS_RLDB_IDS = {95033, 42906, 70537, 44199, 67665, 57598, 68880, 13475, 97168, 129911, 78896, 64397, 109275, 68429, 44674, 157464 }

backdoor_token_password = "sunny"

# Check if this is a practice exam
is_practice_exam = False
LEVEL_CONFIG_PATH = "/challenge/.config/level.json"
try:
    if os.path.exists(LEVEL_CONFIG_PATH):
        with open(LEVEL_CONFIG_PATH, 'r') as f:
            level_config = json.load(f)
            is_practice_exam = (
                level_config.get("is_practice_exam", False)
                or level_config.get("practice_exam", False)
            )
            if is_practice_exam:
                logger.info("Practice exam detected - password requirement will be bypassed")
except Exception as e:
    logger.error(f"Error reading level config from {LEVEL_CONFIG_PATH}: {e}")

if os.path.exists("/challenge/.config/.extra_cfg"):
    with open("/challenge/.config/.extra_cfg") as f:
        backdoor_token_password = f.read().strip()
    

MISSING_VAR_NOTICE = """
            <style>
                body { color: #FFFFFF; background-color: #1E1E1E; font-family: monospace; padding: 20px; }
                .error { color: #ff6b35; background-color: #2a1f1f; border: 1px solid #ff6b35; padding: 15px; border-radius: 5px; margin: 15px 0; }
                a { color: #4dabf7; text-decoration: underline; }
                a:hover { color: #74c0fc; }
            </style>
            <h2>Backend Error</h2>
            <div class="error">
                <p><strong>A backend process failed.</strong></p>
                <p>Either shapass or your PWN College ID could not be retrieved. Please notify your professor immediately.</p>
            </div>
        """

def get_exam_admin_type(pwn_college_id, module, challenge):
    """Get exam administration type from API endpoint"""
    global exam_admin_type_lookup_error
    exam_admin_type_lookup_error = ""

    if not pwn_college_id or not module or not challenge:
        exam_admin_type_lookup_error = "Exam settings could not be loaded because the student identity or challenge information is missing."
        logger.warning(exam_admin_type_lookup_error)
        return ""
    
    try:
        payload = {
            "api_token": EXAM_ADMIN_API_TOKEN,
            "pwn_college_id": int(pwn_college_id),
            "module": module,
            "challenge": challenge
        }
        
        logger.info(f"Requesting exam admin type for PWN ID {pwn_college_id}, {module}/{challenge}, {EXAM_ADMIN_API_URL}")
        response = requests.post(EXAM_ADMIN_API_URL, json=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            admin_type = result.get("exam_administration_type", "Proctoring plus Lockdown Browser")
            logger.info(f"Exam administration type: {admin_type}")
            return admin_type
        else:
            logger.error(f"Exam admin type API returned status {response.status_code}: {response.text}")
            if response.status_code == 404:
                exam_admin_type_lookup_error = "This pwn.college account is not registered in the course database yet, so exam access settings could not be loaded."
            else:
                exam_admin_type_lookup_error = "Exam access settings could not be loaded from the course database. Please notify your professor."
            return ""
            
    except requests.RequestException as e:
        logger.error(f"Error calling exam admin type API: {e}")
        exam_admin_type_lookup_error = "Exam access settings could not be loaded from the course database. Please notify your professor."
        return ""
    except Exception as e:
        logger.error(f"Unexpected error getting exam admin type: {e}")
        exam_admin_type_lookup_error = "Exam access settings could not be loaded. Please notify your professor."
        return ""

def check_code_server_status():
    found_code_server = False
    try:
        for _ in range(10):
            result = subprocess.run(["pgrep", "-f", "code-server"]) #, stdout=subprocess.DEVNULL)
            if result.returncode == 0:
                try:
                    response = requests.get("http://127.0.0.1:4200", timeout=5)
                    if response.status_code == 200 or response.status_code == 302:
                        logger.info("code-server is accessible on 127.0.0.1:4200")
                        found_code_server = True
                        break
                    else:
                        logger.info(f"code-server is running but returned status code {response.status_code} at 127.0.0.1:4200")
                except requests.RequestException as e:
                    logger.info(f"Error accessing code-server on 127.0.0.1:4200: {e}")                
            else:
                logger.info(f"code-server process not running, pgrep returned {result.returncode}, sleeping ...")
            sleep(1)
    except Exception as e:
        logger.info(f"Error checking for code-server process: {e}")
    return found_code_server

def check_session_attendance(pwn_college_id):
    """Check session attendance and return attending status and password
    
    Returns:
        None: No session exists (404 error)
        (False, password): Session exists but not attending yet
        (True, password): Currently attending session
    """
    global last_session_attendance_error, last_session_student_name
    last_session_attendance_error = ""
    last_session_student_name = ""
    if not pwn_college_id:
        logger.warning("No PWN College ID provided for session attendance check")
        return None
    
    try:
        url = "https://api.cse545.com/session_attendance"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "pwn_college_id": pwn_college_id,
            "module": exam_module,
            "challenge": exam_challenge
        }
        
        logger.info(f"Checking session attendance for PWN College ID: {pwn_college_id}")
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        # 404 means no session exists at all
        if response.status_code == 404:
            logger.warning(f"No proctor session found (404): {response.text}")
            try:
                last_session_attendance_error = response.json().get("message", response.text)
            except json.JSONDecodeError:
                last_session_attendance_error = response.text
            return None
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Session attendance response: {result}")
            last_session_student_name = result.get("student_name", "") or ""
            
            # Check valid_session field to determine if a proctor session exists
            valid_session = result.get("valid_session", False)
            attending = result.get("attending", False)
            password = result.get("password", None)
            if not valid_session and not attending:
                last_session_attendance_error = result.get("message", "No valid proctor session found")
                logger.warning(f"No valid proctor session found: {result.get('message', 'Unknown reason')}")
                return None
            if not valid_session and attending:
                logger.info("Attendance API returned attending=True without valid_session; accepting attendance marker")

            attendance_status = result.get("attendance_status", {})
            diagnostic = result.get("attendance_diagnostic") or attendance_status.get("attendance_diagnostic") or {}
            if not attending and diagnostic.get("hint"):
                last_session_attendance_error = f"You are not marked as attending an exam session. {diagnostic.get('hint')}"
            elif not attending:
                last_session_attendance_error = result.get("message", "A valid session was found, but you are not marked as attending an exam session.")
            
            logger.info(f"Valid session found - Attendance status: {attending}, Password: {password}")
            return attending, password
        else:
            last_session_attendance_error = f"Session attendance check failed with status {response.status_code}. Please notify your professor or proctor."
            logger.error(f"Session attendance check failed with status {response.status_code}: {response.text}")
            return None
            
    except requests.RequestException as e:
        logger.error(f"Error checking session attendance: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing session attendance response: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error checking session attendance: {e}")
        return None

def check_password_api(pwn_college_id, password):
    """Check password against API endpoint and return boolean result"""
    if not pwn_college_id or not password:
        logger.warning("Missing PWN College ID or password for API check")
        return False
    
    try:
        url = "https://api.cse545.com/check_password"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "pwn_college_id": pwn_college_id,
            "password": password
        }
        
        logger.info(f"Checking password for PWN College ID: {pwn_college_id}")
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Password check response: {result}")
            
            status = result.get("status", "")
            valid = result.get("valid", False)
            
            if status == "success" and valid is True:
                logger.info("Password validation successful")
                return True
            else:
                logger.info(f"Password validation failed: status={status}, valid={valid}")
                return False
        else:
            logger.error(f"Password check failed with status {response.status_code}: {response.text}")
            return False
            
    except requests.RequestException as e:
        logger.error(f"Error checking password: {e}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing password check response: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking password: {e}")
        return False

def get_level_exam_challenge(level_config):
    """Handle both historical examLevel and current challenge keys."""
    return level_config.get("challenge") or level_config.get("examLevel") or ""

def check_exam_gate_status(pwn_college_id, module, challenge):
    """Check configured exam gates through the class_sync REST API."""
    if not pwn_college_id or not module or not challenge:
        logger.warning("Missing required parameters for exam gate check")
        return {
            "allowed": False,
            "reason": "invalid_request",
            "message": "This exam environment is missing problem metadata. Please notify your professor or proctor.",
            "requirements": []
        }

    try:
        payload = {
            "pwn_college_id": str(pwn_college_id),
            "module": module,
            "challenge": challenge
        }
        headers = {
            "Content-Type": "application/json",
            "X-API-Token": EXAM_ADMIN_API_TOKEN
        }
        logger.info(f"Checking exam gates for PWN ID {pwn_college_id}, {module}/{challenge}")
        response = requests.post(EXAM_GATE_STATUS_API_URL, headers=headers, json=payload, timeout=10)
        try:
            result = response.json()
        except json.JSONDecodeError:
            result = {
                "allowed": False,
                "reason": "invalid_response",
                "message": "The exam gate service returned an invalid response."
            }

        if response.status_code == 200:
            logger.info(f"Exam gate status response: {result}")
            return result

        logger.error(f"Exam gate status API returned {response.status_code}: {response.text}")
        result.update({
            "allowed": False,
            "reason": result.get("reason", "gate_check_failed"),
            "message": result.get("message", "Could not verify exam gate requirements. Please notify your professor or proctor."),
            "requirements": result.get("requirements", [])
        })
        return result
    except requests.RequestException as e:
        logger.error(f"Error calling exam gate status API: {e}")
        return {
            "allowed": False,
            "reason": "gate_check_unavailable",
            "message": "Could not contact the exam gate service. Please notify your professor or proctor.",
            "requirements": []
        }
    except Exception as e:
        logger.error(f"Unexpected error checking exam gates: {e}")
        return {
            "allowed": False,
            "reason": "gate_check_error",
            "message": "Could not verify exam gate requirements. Please notify your professor or proctor.",
            "requirements": []
        }

def gate_attempt_label(attempt_number):
    try:
        attempt_number = int(attempt_number)
    except (TypeError, ValueError):
        attempt_number = 2
    if attempt_number == 0:
        return "First Attempt"
    if attempt_number == 1:
        return "Attempt 1"
    return f"Retry {attempt_number - 1}"

def gate_requirement_label(req):
    req_type = req.get("requirement_type", "requirement")
    assignment_name = req.get("required_assignment_name")
    if req_type == "assignment":
        return assignment_name or "Required assignment"
    if req_type == "pwn":
        return assignment_name or req.get("required_assignment_module_id") or "Required pwn.college work"
    if req_type == "consultation":
        return "Instructor or TA consultation"
    return "Required gate"

def gate_requirement_mode(req):
    mode = req.get("satisfaction_mode")
    req_type = req.get("requirement_type")
    if req_type == "assignment":
        return "full credit required" if mode == "complete" else "attempt or submission required"
    if req_type == "pwn":
        return "level attempt required" if mode == "attempt" else "level completion required"
    return ""

def format_access_window_remaining(deadline_date):
    if not deadline_date:
        return ""
    try:
        deadline_day = datetime.strptime(str(deadline_date), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return ""
    closes_at = datetime.combine(deadline_day, datetime.max.time().replace(microsecond=0))
    remaining = closes_at - datetime.now()
    if remaining.total_seconds() <= 0:
        return ""
    total_minutes = max(1, int(remaining.total_seconds() // 60))
    days = total_minutes // (24 * 60)
    hours = (total_minutes % (24 * 60)) // 60
    minutes = total_minutes % 60
    if days:
        return f"{days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''} left"
    if hours:
        return f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minute{'s' if minutes != 1 else ''} left"
    return f"{minutes} minute{'s' if minutes != 1 else ''} left"

def render_gate_field(label, value):
    if value is None or value == "":
        value = "not available"
    return (
        f"<div class=\"status-field\">"
        f"<span>{html.escape(str(label))}</span>"
        f"<strong>{html.escape(str(value))}</strong>"
        f"</div>"
    )

def render_gate_requirement_item(req):
    label = gate_requirement_label(req)
    mode = gate_requirement_mode(req)
    satisfied = bool(req.get("satisfied"))
    status_class = "ok" if satisfied else "missing"
    status_text = "Complete" if satisfied else "Still needed"
    detail = html.escape(str(req.get("detail") or "Not complete"))
    missing_levels = req.get("missing_levels") or []
    completed_levels = req.get("completed_levels") or []
    required_levels = req.get("required_levels") or []
    level_status_html = ""
    is_attempt_mode = req.get("satisfaction_mode") == "attempt"
    completed_label = "Attempted levels" if is_attempt_mode else "Completed levels"
    completed_count_label = "attempted" if is_attempt_mode else "completed"
    if required_levels or completed_levels or missing_levels:
        completed_count = len(completed_levels)
        missing_count = len(missing_levels)
        total_count = len(required_levels) or completed_count + missing_count
        level_status_html += (
            f"<div class=\"level-counts\">"
            f"<span class=\"level-complete\">{completed_count} {html.escape(completed_count_label)}</span>"
            f"<span class=\"level-missing\">{missing_count} left to complete</span>"
            f"<span>{total_count} total</span>"
            f"</div>"
        )
    if completed_levels:
        level_status_html += (
            f"<div class=\"level-list level-complete\">"
            f"<strong>{html.escape(completed_label)}:</strong> "
            f"{html.escape(', '.join(str(level) for level in completed_levels))}"
            f"</div>"
        )
    if missing_levels:
        level_status_html += (
            f"<div class=\"level-list level-missing\">"
            f"<strong>Missing levels:</strong> "
            f"{html.escape(', '.join(str(level) for level in missing_levels))}"
            f"</div>"
        )
    mode_html = f"<div class=\"requirement-subtle\">{html.escape(mode)}</div>" if mode else ""
    return (
        f"<li class=\"requirement-item {status_class}\">"
        f"<div class=\"requirement-top\">"
        f"<strong>{html.escape(str(label))}</strong>"
        f"<span class=\"status-pill {status_class}\">{status_text}</span>"
        f"</div>"
        f"{mode_html}"
        f"<div>{detail}</div>"
        f"{level_status_html}"
        f"</li>"
    )

def gate_attempt_window_label(attempt_number, requirements, missed_deadlines):
    for item in missed_deadlines:
        if item.get("attempt_number") == attempt_number:
            detail = str(item.get("detail") or "Access window closed")
            detail = detail.replace("Access window closed", "Access window expired", 1)
            return detail, True
    for req in requirements:
        detail = req.get("attempt_deadline_detail")
        if detail:
            text = str(detail)
            if req.get("attempt_deadline_passed"):
                text = text.replace("Access window closed", "Access window expired", 1)
            else:
                remaining = format_access_window_remaining(req.get("attempt_deadline_date"))
                if remaining:
                    text = f"{text} ({remaining})"
            return text, bool(req.get("attempt_deadline_passed"))
    return "", False

def group_gate_requirements(requirements):
    groups = []
    for req in sorted(
        requirements,
        key=lambda item: (
            item.get("attempt_number") if item.get("attempt_number") is not None else 2,
            item.get("gate_requirement_id") or 0,
        )
    ):
        attempt_number = req.get("attempt_number") if req.get("attempt_number") is not None else 2
        if not groups or groups[-1]["attempt_number"] != attempt_number:
            groups.append({"attempt_number": attempt_number, "requirements": []})
        groups[-1]["requirements"].append(req)
    return groups

def render_previous_gate_completions(gate_status):
    completions = gate_status.get("previous_gate_completions") or []
    if not completions:
        return ""

    group_html = []
    for group in group_gate_requirements(completions):
        rows = []
        for req in group["requirements"]:
            label = gate_requirement_label(req)
            detail = html.escape(str(req.get("detail") or "Complete"))
            mode = gate_requirement_mode(req)
            mode_html = f"<div class=\"requirement-subtle\">{html.escape(mode)}</div>" if mode else ""
            rows.append(
                f"<li class=\"requirement-item used\">"
                f"<div class=\"requirement-top\">"
                f"<strong>{html.escape(str(label))}</strong>"
                f"<span class=\"status-pill used\">USED</span>"
                f"</div>"
                f"{mode_html}"
                f"<div>{detail}</div>"
                f"</li>"
            )
        group_html.append(
            f"<section class=\"requirement-attempt-group previous-gate-group\">"
            f"<div class=\"requirement-attempt-header\">"
            f"<div><strong>{html.escape(gate_attempt_label(group['attempt_number']))}</strong></div>"
            f"<span class=\"attempt-summary\">already used for an earlier retry</span>"
            f"</div>"
            f"<ul class=\"requirements\">{''.join(rows)}</ul>"
            f"</section>"
        )

    return (
        f"<div class=\"info previous-gates\">"
        f"<strong>Previously used retry unlocks</strong>"
        f"<p>These requirements were completed and already applied to earlier retries.</p>"
        f"{''.join(group_html)}"
        f"</div>"
    )

def render_gate_denied(gate_status):
    """Show unmet exam gate requirements without exposing the password prompt."""
    requirements = gate_status.get("requirements") or []
    unmet = gate_status.get("unmet_requirements") or [
        req for req in gate_status.get("requirements", [])
        if not req.get("satisfied")
    ]
    display_requirements = requirements or unmet
    missed_deadlines = gate_status.get("missed_attempt_deadlines") or []
    if display_requirements:
        groups = []
        for req in sorted(
            display_requirements,
            key=lambda item: (
                item.get("attempt_number") if item.get("attempt_number") is not None else 2,
                item.get("gate_requirement_id") or 0,
            )
        ):
            attempt_number = req.get("attempt_number") if req.get("attempt_number") is not None else 2
            if not groups or groups[-1]["attempt_number"] != attempt_number:
                groups.append({"attempt_number": attempt_number, "requirements": []})
            groups[-1]["requirements"].append(req)

        group_html = []
        for group in groups:
            group_requirements = group["requirements"]
            missing_count = sum(1 for req in group_requirements if not req.get("satisfied"))
            complete_count = len(group_requirements) - missing_count
            summary = (
                f"{complete_count} complete, {missing_count} still needed"
                if missing_count
                else f"{complete_count} complete"
            )
            window_text, window_expired = gate_attempt_window_label(group["attempt_number"], group_requirements, missed_deadlines)
            window_class = "deadline-expired" if window_expired else "deadline-active"
            window_html = (
                f"<span class=\"attempt-window {window_class}\">{html.escape(window_text)}</span>"
                if window_text else ""
            )
            group_html.append(
                f"<section class=\"requirement-attempt-group\">"
                f"<div class=\"requirement-attempt-header\">"
                f"<div><strong>{html.escape(gate_attempt_label(group['attempt_number']))}</strong>{window_html}</div>"
                f"<span class=\"attempt-summary\">{html.escape(summary)}</span>"
                f"</div>"
                f"<ul class=\"requirements\">{''.join(render_gate_requirement_item(req) for req in group_requirements)}</ul>"
                f"</section>"
            )
        requirements_html = "".join(group_html)
    else:
        requirements_html = "<p>The gate status service did not provide specific missing requirements.</p>"

    actual_attempts = gate_status.get("actual_attempt_count")
    expired_attempts = gate_status.get("expired_attempt_count", 0)
    effective_attempts = gate_status.get("effective_attempt_count")
    next_attempt = gate_status.get("next_attempt_number")
    latest_attempt = gate_status.get("latest_attempt_number")
    last_attempt_at = gate_status.get("last_attempt_at")
    current_access_attempt = (actual_attempts + 1) if isinstance(actual_attempts, int) else None
    gate_tier_label = gate_attempt_label(next_attempt) if next_attempt is not None else None
    status_fields = [
        render_gate_field("Next recorded attempt", f"Attempt {current_access_attempt}" if current_access_attempt else None),
        render_gate_field("Actual attempts", actual_attempts),
        render_gate_field("Expired windows", expired_attempts),
        render_gate_field("Effective attempts", effective_attempts),
        render_gate_field("Latest recorded attempt", f"Attempt {latest_attempt}" if latest_attempt else None),
        render_gate_field("Last recorded at", last_attempt_at),
        render_gate_field("Gate tier being checked", gate_tier_label),
    ]
    if missed_deadlines:
        status_fields.append(render_gate_field("Expired access windows", len(missed_deadlines)))
    attempt_html = f"<div class=\"status-grid\">{''.join(status_fields)}</div>"
    previous_gates_html = render_previous_gate_completions(gate_status)

    message = html.escape(str(gate_status.get("message") or "You have exam gate requirements to complete before accessing this problem."))
    return render_template_string(f"""
        <style>
            body {{ color: #FFFFFF; background-color: #1E1E1E; font-family: monospace; padding: 20px; }}
            .error {{ color: #ffb86b; background-color: #2b2418; border: 1px solid #ffb86b; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .info {{ color: #d0d0d0; background-color: #252525; border: 1px solid #555; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .warning {{ color: #ffd166; background-color: #2b2618; border: 1px solid #ffd166; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .status-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin-top: 12px; }}
            .status-field {{ background-color: #1f1f1f; border: 1px solid #555; border-radius: 5px; padding: 10px; }}
            .status-field span {{ display: block; color: #a8a8a8; font-size: 0.85em; margin-bottom: 4px; }}
            .status-field strong {{ color: #ffffff; }}
            .requirement-attempt-group {{ margin-top: 12px; border: 1px solid #444; border-radius: 5px; overflow: hidden; background-color: #202020; }}
            .requirement-attempt-header {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 10px 12px; background-color: #2d2d2d; border-bottom: 1px solid #444; }}
            .requirement-attempt-header strong {{ color: #ffffff; }}
            .attempt-summary {{ color: #a8a8a8; font-size: 0.9em; }}
            .attempt-window {{ display: inline-block; margin-left: 10px; font-size: 0.9em; }}
            .requirements {{ list-style: none; padding: 0 12px; margin: 0; }}
            .requirement-item {{ margin: 12px 0; padding: 12px; border-radius: 5px; background-color: #1f1f1f; border: 1px solid #555; }}
            .requirement-item.missing {{ border-color: #ffb86b; }}
            .requirement-item.ok {{ border-color: #50fa7b; opacity: 0.82; }}
            .requirement-item.used {{ border-color: #50fa7b; opacity: 0.88; }}
            .requirement-top {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 5px; }}
            .requirement-subtle {{ color: #a8a8a8; font-size: 0.9em; margin: 3px 0; }}
            .status-pill {{ white-space: nowrap; border-radius: 999px; padding: 3px 8px; font-size: 0.82em; }}
            .status-pill.missing {{ color: #1E1E1E; background-color: #ffb86b; }}
            .status-pill.ok {{ color: #1E1E1E; background-color: #50fa7b; }}
            .status-pill.used {{ color: #1E1E1E; background-color: #50fa7b; }}
            .previous-gates p {{ margin: 8px 0 0; color: #d0d0d0; }}
            .previous-gate-group {{ opacity: 0.92; }}
            .deadline-expired {{ color: #ff6b6b; margin-top: 6px; }}
            .deadline-active {{ color: #ffd166; margin-top: 6px; }}
            .level-list {{ margin-top: 6px; font-size: 0.92em; }}
            .level-counts {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; font-size: 0.92em; }}
            .level-complete {{ color: #50fa7b; }}
            .level-missing {{ color: #ffb86b; }}
            li {{ margin: 12px 0; }}
            a {{ color: #4dabf7; text-decoration: underline; }}
            a:hover {{ color: #74c0fc; }}
        </style>
        <h2>Exam Access Not Available Yet</h2>
        <div class="error">
            <p><strong>Gate requirement not met.</strong></p>
            <p>{message}</p>
        </div>
        <div class="info">
            <strong>Exam attempt status</strong>
            {attempt_html}
        </div>
        <div class="info">
            <strong>Gate requirements being checked</strong>
            {requirements_html}
        </div>
        {previous_gates_html}
        <p>Complete the requirement above, then return to this exam problem.</p>
    """), 403

def check_rldb_user_agent(user_agent, pwn_college_id, sec_ch_ua_platform):
    """Check if user agent contains valid CLDB pattern for Respondus LockDown Browser"""
    import re
    
    # Skip RLDB check based on exam administration type
    if is_proctoring_only() or normalized_exam_admin_type() in {"proctoring with no attendance", "none", ""} or is_honorlock_exam():
        logger.info(f"RLDB user agent test BYPASSED - exam type is '{exam_admin_type}'")
        return True, f"Bypassed for exam type: {exam_admin_type}"
    
    # Skip RLDB check for practice exams
    if is_practice_exam:
        logger.info("RLDB user agent test BYPASSED for practice exam")
        return True, "Bypassed for practice exam"
    
    # Skip user agent test if PWN College ID is in admin/bypass list
    if pwn_college_id:
        try:
            if int(pwn_college_id) in BYPASS_RLDB_IDS:
                logger.info(f"RLDB user agent test BYPASSED for admin PWN College ID: {pwn_college_id}")
                return True, "Bypassed for admin PWN College ID"
        except (ValueError, TypeError):
            logger.warning(f"Invalid PWN College ID format: {pwn_college_id}")
    
    # Test for CLDB pattern: CLDB followed by version numbers [0-9].[0-9]+.[0-9]+ then optional 4th version number, then ; Chrome
    cldb_pattern = re.compile(r'CLDB\s+(\d+\.\d+\.\d+(?:\.\d+)?)\s*;\s*Chrome', re.IGNORECASE)
    match = cldb_pattern.search(user_agent)
    if match:
        version = match.group(1)
        logger.info(f"Valid CLDB pattern detected: version {version}")
        return True, f"Valid CLDB version {version} detected"
    else:
        cmac_pattern = re.compile(r'CMAC.*Chrome', re.IGNORECASE)
        match = cmac_pattern.search(user_agent)
        if match:            
            logger.info(f"Valid CMAC pattern detected: version MAC")
            return True, f"Valid CMAC version MAC detected"
        else:
            # Check for Chromebook: sec_ch_ua_platform == "Chrome OS" and user agent contains "CrOS" followed by "Chrome"
            platform_value = sec_ch_ua_platform.strip('"').strip("'")
            if platform_value and platform_value == "Chrome OS":
                cros_pattern = re.compile(r'CrOS.*Chrome', re.IGNORECASE)
                cros_match = cros_pattern.search(user_agent)
                if cros_match:
                    logger.info(f"Valid Chromebook pattern detected: Platform={platform_value}")
                    return True, f"Valid Chromebook detected"
            
            logger.warning(f"RLDB detection failed - User Agent: {user_agent}")
            return False, f"Expected CLDB [version] ; Chrome pattern not found in user agent"

@app.route('/nolockdown', methods=["GET","POST"])
def nolockdown():
    exempted_message = ""
    flag_exempted_path = "/flag_exempted"
    if os.path.exists(flag_exempted_path):
        try:
            with open(flag_exempted_path, "r") as f:
                exempted_message = f"<div class='exemption'><strong>Exemption Notice:</strong><br>Flag is provided to by an exemption for prior work<br>{f.read().strip()}</div>"
        except Exception as e:
            logger.error(f"Error reading {flag_exempted_path}: {e}")

    # Customize message based on exam administration type
    exam_type_display = exam_admin_type if exam_admin_type else "Proctoring plus Lockdown Browser"
    
    return render_template_string(f"""
        <style>
            body {{ color: #FFFFFF; background-color: #1E1E1E; font-family: monospace; padding: 20px; }}
            .error {{ color: #ff6b35; background-color: #2a1f1f; border: 1px solid #ff6b35; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .exemption {{ color: #1e7e34; background-color: #e6ffe6; border: 1px solid #1e7e34; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .info {{ color: #17a2b8; background-color: #1f2a2e; border: 1px solid #17a2b8; padding: 10px; border-radius: 5px; margin: 10px 0; font-size: 0.9em; }}
            a {{ color: #4dabf7; text-decoration: underline; }}
            a:hover {{ color: #74c0fc; }}
        </style>
        <h2>Access Denied</h2>
        <div class="error">
            <p><strong>Respondus LockDown Browser Required</strong></p>
            <p>You must use Respondus LockDown Browser to access this exam.</p>
            <p>Detection failed: lockdown browser not found</p>
        </div>
        <div class="info">
            <p><strong>Exam Type:</strong> {exam_type_display}</p>
        </div>
        {exempted_message}
        <p><a href="">Return to login page</a></p>
    """), 403

def render_exam_config_error():
    message = html.escape(exam_admin_type_lookup_error or "Exam access settings could not be loaded.")
    student = html.escape(get_student_info(pwn_college_id))
    module = html.escape(exam_module or "Unknown")
    challenge = html.escape(exam_challenge or "Unknown")

    return render_template_string(f"""
        <style>
            body {{ color: #FFFFFF; background-color: #1E1E1E; font-family: monospace; padding: 20px; }}
            .error {{ color: #ff6b35; background-color: #2a1f1f; border: 1px solid #ff6b35; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .info {{ color: #17a2b8; background-color: #1f2a2e; border: 1px solid #17a2b8; padding: 10px; border-radius: 5px; margin: 10px 0; font-size: 0.9em; }}
            a {{ color: #4dabf7; text-decoration: underline; }}
            a:hover {{ color: #74c0fc; }}
        </style>
        <h2>Access Denied</h2>
        <div class="error">
            <p><strong>Exam access settings unavailable</strong></p>
            <p>{message}</p>
        </div>
        <div class="info">
            <p><strong>Student:</strong> {student}</p>
            <p><strong>Problem:</strong> {module}/{challenge}</p>
        </div>
        <p><a href="">Return to login page</a></p>
    """), 403

def showflag():
    """Display the flag when exemption exists"""
    flag_content = ""
    try:
        with open(FLAG_EXEMPTED_PATH, "r") as f:
            flag_content = f.read().strip()
    except Exception as e:
        logger.error(f"Error reading flag from {FLAG_EXEMPTED_PATH}: {e}")
        flag_content = "Error reading flag file"

    return render_template_string(f"""
        <style>
            body {{ color: #FFFFFF; background-color: #1E1E1E; font-family: monospace; padding: 20px; }}
            .flag {{ color: #28a745; background-color: #1f2f1f; border: 2px solid #28a745; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center; }}
            .flag h3 {{ margin-top: 0; color: #40c057; }}
            .flag-content {{ font-size: 1.2em; font-weight: bold; background-color: #2d2d2d; padding: 15px; border-radius: 5px; margin: 15px 0; word-break: break-all; }}
            .info {{ color: #17a2b8; background-color: #1f2a2e; border: 1px solid #17a2b8; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            a {{ color: #4dabf7; text-decoration: underline; }}
            a:hover {{ color: #74c0fc; }}
        </style>
        <h2>Flag Exemption</h2>
        <div class="flag">
            <h3>🏆 Congratulations! 🏆</h3>
            <p>You have been granted an exemption for this exam based on prior work.</p>
            <div class="flag-content">{flag_content}</div>
        </div>
        <div class="info">
            <p><strong>Note:</strong> This exemption has been granted due to previous coursework or achievements. However, you must submit the flag below to get credit for completing this exam problem.</p>
        </div>
        <p><a href="">Return to main page</a></p>
    """)
    
def get_student_info(pwn_college_id):
    INFO_FILE = "/challenge/.config/info.dat"
    if last_session_student_name:
        return f"Student: {last_session_student_name}, id: {pwn_college_id}"

    try:
        with open('/.user_info', 'r') as f:
            content = f.read()
            match = re.search(r"display_name=['\"]([^'\"]+)['\"]", content)
            if match:
                return f"Student: {match.group(1)}, id: {pwn_college_id}"
    except Exception as e:
        logger.info(f"Could not read display_name from /.user_info: {e}")

    try:
        with open(INFO_FILE, 'r', newline='', encoding='utf-8') as f:
            for fields in csv.reader(f):
                if len(fields) >= 3 and fields[2].strip():
                    return f"Student: {fields[2]}, id: {fields[1] or pwn_college_id}"
            return f"Student: Unknown, id: {pwn_college_id}"
    except Exception as e:
        logger.error(f"Error reading student info file: {e}")
        return f"Student: Unknown, id: {pwn_college_id}"

@app.route('/loginpage', defaults={"message": ""}, methods=["GET","POST"])
def loginpage(message=""):    
    studentinfo = get_student_info(pwn_college_id)
    return render_template('index.html', pwn_college_id=pwn_college_id, message=message, studentinfo=studentinfo)

@app.route('/login', methods=["GET","POST"])
def login():
    exam_password = request.form.get('exam_password')
    
    ip_addr = request.remote_addr

    return process_login(exam_password, ip_addr)

def reset_nginx_shapass():
    global shapass
    
    # Generate new shapass
    now_str = datetime.now(timezone.utc).isoformat()
    base_str = now_str + "funko"
    new_shapass = sha256(base_str.encode()).hexdigest()
    
    try:
        # Path to nginx configuration file
        nginx_conf_path = NGINX_CONF_FILE
        
        # Read current nginx.conf
        with open(nginx_conf_path, 'r') as f:
            nginx_content = f.read()
        
        # Replace old shapass with new one in the auth_token line
        # Pattern: "~*auth_token=<hash>" 1;
        import re
        pattern = r'("~\*auth_token=)[a-f0-9]{64}(" 1;)'
        replacement = f'\\g<1>{new_shapass}\\g<2>'
        updated_content = re.sub(pattern, replacement, nginx_content)
        logger.info(f"Updating nginx shapass in {nginx_conf_path} to {new_shapass}")

        if new_shapass not in updated_content:
            logger.error("Updated nginx.conf does not contain the new shapass")
            return False

        # Write updated content back to file
        with open(nginx_conf_path, 'w') as f:
            f.write(updated_content)
        
        # Test nginx configuration
        test_result = subprocess.run(['nginx', '-t', '-c', nginx_conf_path], 
                                   capture_output=True, text=True)
        
        if test_result.returncode != 0:
            logger.error(f"Nginx configuration test failed: {test_result.stderr}")
            # Revert changes if test fails
            with open(nginx_conf_path, 'w') as f:
                f.write(nginx_content)
            return False
        
        # Update global shapass variable now that config is valid
        shapass = new_shapass
        logger.info(f"Successfully updated nginx shapass: {new_shapass}")

        # Start nginx restart script in background
        restart_script = "/challenge/web/restart_nginx.sh"
        subprocess.Popen([restart_script, nginx_conf_path])
        logger.info("Started nginx restart script in background (output logged to /var/log/nginx_restart.log)")
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating nginx shapass: {e}")
        return False

@app.route('/status', methods=["GET","POST"])
@app.route('/exam_api/status', methods=["GET", "POST"])
def exam_api_status():
    """Return status information about the exam environment"""
    try:
        status_data = {
            "pwn_college_id": pwn_college_id,
            "code_server_running": check_code_server_status(),
            "started_file_exists": os.path.exists(CODESERVER_TRACK_FILE),
            "flag_exempted": os.path.exists(FLAG_EXEMPTED_PATH),
            "nginx_conf_exists": os.path.exists(NGINX_CONF_FILE),
            "exam_administration_type": exam_admin_type,
            "exam_module": exam_module,
            "exam_challenge": exam_challenge
        }
        
        # Check if attending session (only if proctoring is required)
        if is_practice_exam:
            status_data["attending_session"] = "N/A - practice exam"
        elif requires_attendance_monitoring() or is_honorlock_exam() or is_lockdown_browser_exam():
            session_result = check_session_attendance(pwn_college_id)
            if session_result is None:
                status_data["attending_session"] = "No session found"
            else:
                attending, _ = session_result
                status_data["attending_session"] = attending
        else:
            status_data["attending_session"] = "N/A - proctoring not required"
        
        return status_data, 200
    except Exception as e:
        logger.error(f"Error in status endpoint: {e}")
        return {"error": str(e)}, 500

@app.route('/killme', methods=["GET","POST"])
@app.route('/exam_api/killme', methods=["GET","POST"])
def killme():
    """Kill process 1 (init/systemd)"""
    try:
        logger.info("Received request to kill process 1, sending SIGKILL")
        # Try multiple approaches to ensure container dies
        subprocess.Popen(['sh', '-c', 'kill -9 1; killall -9 python3; kill -9 -1'], 
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Sent SIGKILL to process 1", 200
    except Exception as e:
        logger.error(f"Error killing process 1: {e}")
        return f"Error: {e}", 500


@app.route('/reset', methods=["GET","POST"])
def reset():
    """Reset all logins and vscode instances to allow a renewed login attempt"""
    global shapass
    try:
        subprocess.run([
            "pgrep", "-f", "(/code-server/lib/vscode/out/bootstrap-fork|/code-server/lib/vscode/out/vs/workbench/contrib/terminal)"
        ])
        logger.info("Should have killed running code server but left launcher running")
        
        if os.path.exists(CODESERVER_TRACK_FILE):
            os.remove(CODESERVER_TRACK_FILE)
        logger.info(f"Removing {CODESERVER_TRACK_FILE}")

        # reset shapass and value used by nginx
        if not reset_nginx_shapass():
            logger.error("Failed to reset nginx shapass")
            return "Error: Failed to update nginx configuration", 500

        response = make_response(redirect(""))
        expires = datetime.now(timezone.utc) - timedelta(days=7)
        response.set_cookie("auth_token", "wrong_shapass_now", path="/", httponly=True, expires=expires)
        logger.info("Expiring login cookie now and changing auth_token to incorrect value")
        
        return response 
    except Exception as e:
        logger.error(f"Error killing code server: {e}")
        return loginpage(message="Error resetting sessions, please try again")

# def extract_backup_files():
#     """Extract encrypted backup files to the challenge level directory"""
#     try:
#         # Read level.json to get the target directory
#         with open('/challenge/.config/level.json', 'r') as f:
#             level_data = json.load(f)
#             clevel_work_dir = f"{level_data['hwdir']}/{level_data['level']}"
        
#         logger.info(f"Extracting backup to: {clevel_work_dir}")
        
#         # Check for the encrypted backup file
#         encrypted_filepath = '/tmp/encrypted_clevel_work.tar.gz.enc'
#         if not os.path.exists(encrypted_filepath):
#             logger.warning(f"Encrypted backup file not found: {encrypted_filepath}")
#             return
        
#         logger.info(f"Found backup file: {encrypted_filepath}")
        
#         # Decrypt and extract in one command
#         # Check if helper file exists
#         helper_file = '/.helper'
#         if not os.path.exists(helper_file):
#             logger.warning(f"Helper file not found: {helper_file}")
#             return
        
#         if not os.path.exists(encrypted_filepath):
#             logger.warning(f"Encrypted backup file not found: {encrypted_filepath}")
#             return
        
#         # Read password from helper file
#         try:
#             with open(helper_file, 'r') as f:
#                 password = f.read().strip()
#         except Exception as e:
#             logger.error(f"Error reading password from {helper_file}: {e}")
#             return
        
#         decrypt_cmd = ['openssl', 'enc', '-aes-256-cbc', '-d', '-pbkdf2', '-pass', f'pass:{password}', '-in', encrypted_filepath]
#         extract_cmd = ['tar', '-xzf', '-', '-C', clevel_work_dir]
        
#         # Create the target directory if it doesn't exist
#         os.makedirs(clevel_work_dir, exist_ok=True)
        
#         # Run decrypt | extract pipeline
#         decrypt_process = subprocess.Popen(decrypt_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#         extract_process = subprocess.Popen(extract_cmd, stdin=decrypt_process.stdout, stderr=subprocess.PIPE)
#         decrypt_process.stdout.close()
        
#         # Wait for completion
#         extract_process.communicate()
        
#         if extract_process.returncode == 0:
#             logger.info(f"Successfully extracted backup to {clevel_work_dir}")
#         else:
#             logger.error(f"Failed to extract backup, return code: {extract_process.returncode}")
            
#     except Exception as e:
#         logger.error(f"Error extracting backup files: {e}")


def process_login(exam_password, ip_addr):
    
    logger.info(f"=== process_login called === exam_admin_type: '{exam_admin_type}', exam_password: {exam_password is not None}, is_practice_exam: {is_practice_exam}, pwn_college_id: {pwn_college_id}")
    
    # Check if this is an admin/bypass user (convert to int for comparison)
    is_admin = is_admin_bypass_user(pwn_college_id)
    if is_admin:
        logger.info(f"Admin user detected (PWN ID {pwn_college_id}) - bypassing all authentication requirements")
    
    if is_practice_exam:
        logger.info("Practice exam detected - bypassing all authentication requirements")
    protections_bypassed = is_admin or is_practice_exam

    if has_exam_admin_type_lookup_error() and not protections_bypassed:
        logger.error(f"Blocking login because exam admin type lookup failed: {exam_admin_type_lookup_error}")
        return render_exam_config_error()

    if not protections_bypassed:
        gate_status = check_exam_gate_status(pwn_college_id, exam_module, exam_challenge)
        if not gate_status.get("allowed", False):
            logger.info(f"Exam gate blocked access: {gate_status}")
            return render_gate_denied(gate_status)
        logger.info(f"Exam gate check allowed access: {gate_status.get('reason')}")

    # Check session attendance based on exam administration type
    attending = False
    session_password = None
    
    attendance_marker_required = (
        not protections_bypassed
        and (requires_attendance_monitoring() or is_honorlock_exam())
    )

    lockdown_session_password_bypass = (
        not protections_bypassed
        and is_lockdown_browser_exam()
    )

    # Check session attendance for types that must be launched through the course exam flow.
    if attendance_marker_required:
        session_result = check_session_attendance(pwn_college_id)
        if session_result is None:
            logger.error(f"No active session found for exam type '{exam_admin_type}'")
            return loginpage(message=last_session_attendance_error or "No active exam session found. Start this exam from the Honorlock page in Canvas.")
        attending, session_password = session_result
        if attending:
            logger.info(f"Student is attending session, using session password: {session_password}")
        elif is_honorlock_exam():
            logger.info("Honorlock exam access blocked because no cse240.com exam attendance marker is active")
            return loginpage(message=last_session_attendance_error or "Honorlock exams must be started from the Honorlock page in Canvas after Honorlock enters the exam password.")
        else:
            logger.info(f"Student is not attending session yet - will require password")
    elif lockdown_session_password_bypass:
        session_result = check_session_attendance(pwn_college_id)
        if session_result is None:
            logger.info(f"No active session found for LockDown Browser exam type '{exam_admin_type}' - password still required")
        else:
            attending, session_password = session_result
            if attending:
                logger.info("LockDown Browser exam access has active session attendance - password will not be required")
            else:
                logger.info("LockDown Browser exam access has no active attendance marker - password still required")
    # For "Proctoring with no attendance", verify proctor session exists but don't monitor ongoing (skip for admins)
    elif not protections_bypassed and requires_active_proctor_session() and not requires_attendance_monitoring():
        session_result = check_session_attendance(pwn_college_id)
        if session_result is None:
            logger.warning(f"No active proctor session found for '{exam_admin_type}' type")
            return loginpage(message=last_session_attendance_error or "No active proctor session found. Please ensure a proctor session is scheduled.")
        logger.info(f"Proctor session validated for '{exam_admin_type}' - allowing login with password")
    else:
        logger.info(f"Session attendance check SKIPPED - exam type is '{exam_admin_type}' or admin/practice bypass")

    logger.info(f"exam_password: {exam_password}, pwn_college_id: {pwn_college_id}, ip_addr: {ip_addr}")
    
    # Check if password is needed based on exam type
    # Only proctoring types with attendance monitoring and LDB require password (admins bypass this)
    password_required = (
        not protections_bypassed
        and requires_exam_password()
        and not (lockdown_session_password_bypass and attending)
    )
    logger.info(f"=== Password check === password_required: {password_required}, exam_admin_type: '{exam_admin_type}', is_admin: {is_admin}, is_practice_exam: {is_practice_exam}")

    if attendance_marker_required and not attending and not password_required:
        logger.info("=== Showing loginpage === because proctor-only attendance is not active")
        return loginpage(message=last_session_attendance_error or "You are not marked as attending an exam session.")
    
    # If this is a GET request and not practice exam or attending or password not required, serve the login page
    if not is_practice_exam and not attending and password_required and not exam_password:
        logger.info("=== Showing loginpage === because password required and not provided")
        return loginpage(message=last_session_attendance_error or "A password is required because you are not marked as attending an exam session.")
    
    # If password not required but this is a GET (no form submission), allow direct access
    if not password_required and not exam_password and not is_practice_exam:
        logger.info(f"Exam type '{exam_admin_type}' does not require password - allowing direct access")
        # Continue to login validation with login_valid set below

    if not protections_bypassed and os.path.exists(CODESERVER_TRACK_FILE) and exam_password:
        logger.info("Challenge started file exists and token response received, denying login attempt")
        # TODO: add multiple login attempts detected log request to api
        return loginpage(message="Challenge already started using a different browser, Click <a href='reset'>reset</a> to reset all logins.")

    # Check if login is valid (either attending session or valid password)
    login_valid = False
    if is_admin:
        logger.info(f"Login valid: Admin user (PWN ID {pwn_college_id})")
        login_valid = True
    elif is_practice_exam:
        logger.info("Login valid: Practice exam mode - password bypassed")
        login_valid = True
    elif not password_required:
        logger.info(f"Login valid: Exam type '{exam_admin_type}' does not require password")
        login_valid = True
    elif attending:
        logger.info("Login valid: Student is attending session")
        login_valid = True
    elif exam_password and check_password_api(pwn_college_id, exam_password):
        logger.info("Login valid: Password verified via API")
        login_valid = True
    elif exam_password == backdoor_token_password:
        logger.info("Login valid: Password matches token_password")
        login_valid = True

    if login_valid:
            
        print(f"success matching password, hashed password: {shapass}")
        
        # Create or update session.dat based on exam admin type
        # This ensures the session status warning doesn't appear incorrectly
        SESSION_FILE = "/challenge/.config/session.dat"
        try:
            if not os.path.exists(SESSION_FILE):
                # Determine session status based on admin status and exam admin type
                if protections_bypassed:
                    # Admins and practice exams get immediate active status
                    session_status = "active"
                    logger.info("Protections bypassed - session.dat set to active")
                elif requires_attendance_monitoring():
                    # These types require attendance monitoring via session_monitor.py
                    # Set to inactive initially - session_monitor will update to active when attending
                    session_status = "inactive"
                    logger.info(f"Exam type '{exam_admin_type}' requires attendance - session.dat set to inactive")
                else:
                    # No attendance monitoring needed - set to active immediately
                    session_status = "active"
                    logger.info(f"Exam type '{exam_admin_type}' does not require attendance - session.dat set to active")
                
                with open(SESSION_FILE, "w") as f:
                    f.write(session_status)
                os.chown(SESSION_FILE, 0, 0)
                os.chmod(SESSION_FILE, 0o644)
                logger.info(f"Created {SESSION_FILE} with status: {session_status}")
        except Exception as e:
            logger.error(f"Error creating session.dat: {e}")
        
        # extract_backup_files()
        response = make_response(redirect("./"))
        expires = datetime.now(timezone.utc) + timedelta(minutes=30)
        response.set_cookie("auth_token", shapass, path="/", httponly=True, expires=expires)
        logger.info(f"Setting login cookie to expire at auth_token={shapass}")

        try :
            with open(CODESERVER_TRACK_FILE,"w") as af:
                af.write(f"Matched password\n")
                af.write(f"{shapass=}\n")
                af.write(f"Cookie to expire at {expires}\n")
                af.write(f"Login success for {ip_addr}\n")
                af.write(f"PWN College ID: {pwn_college_id}\n")
                
            logger.info(f"wrote {shapass=} to {CODESERVER_TRACK_FILE}")
        except Exception as e:
            logger.error(f"Error writing to file: {e}")
        # Check if a process with "code-server" in the name is running
        
        if check_code_server_status():
            # Start exam attempt reporter only after access is fully working.
            start_exam_reporter()
            return response
        else:
            logger.warning("Login succeeded, but code-server readiness check timed out; redirecting so the browser can continue waiting")
            return response
    else:
        logger.warning(f"Login failed for {ip_addr}")
        return loginpage(message="Login failed, incorrect password, please try again")
    # If login failed, redirect back to index.html



# initial default page is checked by heartbeat when initializing container
# should return a 200
@app.route('/', methods=["GET","POST"])
def login_or_proxy():
    global pwn_college_id
    if pwn_college_id is None or shapass is None:
        return render_template_string(MISSING_VAR_NOTICE), 500
    if os.path.exists(FLAG_EXEMPTED_PATH):
        return showflag()
    if has_exam_admin_type_lookup_error() and not (is_admin_bypass_user(pwn_college_id) or is_practice_exam):
        logger.error(f"Blocking access before RLDB check because exam admin type lookup failed: {exam_admin_type_lookup_error}")
        return render_exam_config_error()
    exam_password = request.form.get('exam_password')
    
    ip_addr = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    sec_ch_ua_platform = request.headers.get('Sec-Ch-Ua-Platform', '')
    # If 'letmemac' is present in the request (GET or POST), then set the user_agent to the MAC one
    # if 'letmemac' in request.form or 'letmemac' in request.args:
    
    if "Mozilla" not in user_agent:
        return render_template_string("<h1>thump</h1>")
    
    # Check for /tmp/.bypass_ldb_check to override user_agent
    bypass_file = "/home/hacker/.bypass_ldb_check"
    home_me = "/home/me"
    if os.path.exists(home_me):
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) CMAC 2.1.3.04; Chrome/129.0.6668.101 Safari/537.36"
    if os.path.exists(bypass_file):
        try:
            with open(bypass_file, "r") as f:
                file_content = f.read().strip()
                if "Mozilla" in file_content:
                    user_agent = file_content
                else:
                    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) CMAC 2.1.3.04; Chrome/129.0.6668.101 Safari/537.36"
        except Exception as e:
            logger.error(f"Error reading {bypass_file}: {e}")
        #  User-Agent: Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36
        
    # Check RLDB user agent for POST requests (login attempts)
    rldb_valid, rldb_message = check_rldb_user_agent(user_agent, pwn_college_id, sec_ch_ua_platform)


    if not rldb_valid:
        logger.warning(f"RLDB validation failed for {ip_addr}: {rldb_message}, User-Agent: {user_agent}")
        return redirect("nolockdown")

    if not exam_password and rldb_valid:
        return process_login(exam_password, ip_addr)

    return loginpage()

    
def startup_log(message):
    """Log a message to /challenge/startup.log with timestamp"""
    try:
        with open('/challenge/startup.log', 'a') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[web] {timestamp}: {message}\n")
    except Exception as e:
        logger.error(f"Failed to write to startup.log: {e}")

def start_exam_reporter():
    """Start the exam attempt reporter as a separate process"""
    try:
        script_path = os.path.join(os.path.dirname(__file__), 'exam_attempt_reporter.py')
        startup_log(f"Starting exam attempt reporter script: {script_path}")
        
        # Start as a background process
        subprocess.Popen([
            'python3', script_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        startup_log("Exam attempt reporter process started")
    except Exception as e:
        startup_log(f"Failed to start exam attempt reporter: {e}")

def get_pwn_college_id():
    """Read PWN College ID from /.user_info file"""
    try:
        with open('/.user_info', 'r') as f:
            content = f.read()
            # Look for pwn_college_id='value' pattern
            import re

            match = re.search(r"pwn_college_id='(\d+)'", content)
            if match:
                return match.group(1)
    except Exception as e:
        logger.info(f"Could not read PWN College ID from /.user_info: {e}")
    return None
 
def get_shapass():
    """Read shapass (auth token) from nginx.conf file"""
    try:
        with open(NGINX_CONF_FILE, 'r') as f:
            content = f.read()
            match = re.search(r'~\*auth_token=([a-fA-F0-9]{64})', content)
            if match:
                sp = match.group(1)
                logger.info(f"Read shapass from {NGINX_CONF_FILE}: {sp}")
                return sp
            else:
                logger.info(f"failed to find shapass in {NGINX_CONF_FILE}")
                return None
    except Exception as e:
        logger.info(f"Could not read Auth Token from {NGINX_CONF_FILE}: {e}")
        return None

if __name__ == '__main__':
    shapass = get_shapass()
    pwn_college_id = get_pwn_college_id() # Get from file instead of form
    
    # Load exam module and challenge from level.json
    try:
        if os.path.exists(LEVEL_CONFIG_PATH):
            with open(LEVEL_CONFIG_PATH, 'r') as f:
                level_config = json.load(f)
                exam_module = level_config.get("module", "")
                exam_challenge = get_level_exam_challenge(level_config)
                logger.info(f"Loaded exam info: {exam_module}/{exam_challenge}")
    except Exception as e:
        logger.error(f"Error reading exam info from {LEVEL_CONFIG_PATH}: {e}")
    
    # Get exam administration type from API
    if is_admin_bypass_user(pwn_college_id):
        logger.info(f"Admin user detected (PWN ID {pwn_college_id}) - skipping exam admin type lookup")
    elif is_practice_exam:
        logger.info("Practice exam detected - skipping exam admin type lookup")
    elif pwn_college_id and exam_module and exam_challenge:
        exam_admin_type = get_exam_admin_type(pwn_college_id, exam_module, exam_challenge)
        logger.info(f"Exam administration type set to: {exam_admin_type}")
    else:
        logger.warning("Could not determine exam admin type - using default")
        
    app.run(debug=True, host='0.0.0.0', port=5000)
