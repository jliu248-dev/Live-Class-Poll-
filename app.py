import itertools
import secrets
import socket
import threading

from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for,
)
from werkzeug.exceptions import HTTPException

# Port 5000 is taken by AirPlay Receiver on macOS, so use 8000 instead.
PORT = 8000

MAX_QUESTION_LENGTH = 200
MAX_OPTION_LENGTH = 80
MIN_OPTIONS = 2
MAX_OPTIONS = 6

app = Flask(__name__)
# A fresh key each run is fine: all poll data is in memory and resets on restart anyway.
app.secret_key = secrets.token_hex(32)


# --- In-memory storage (everything resets when the server restarts) ---

# question id -> {"id", "text", "options", "votes", "voters", "open"}
questions = {}
# question ids in the order the teacher created them
question_order = []


def new_join_code():
    return f"{secrets.randbelow(10000):04d}"


# current_id: which question is on the projector (None = nothing showing)
# join_code: the 4-digit code students type to join
state = {"current_id": None, "join_code": new_join_code()}

next_question_id = itertools.count(1)
# The dev server handles requests on several threads, so guard every change.
lock = threading.Lock()


def lan_address():
    """Best guess at this computer's address on the local network, for the join link."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # No packet is sent; this just asks the OS which interface it would use.
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def site_address():
    """Short address students type to reach the site (no http:// needed in most browsers)."""
    return f"{lan_address()}:{PORT}"


def has_joined():
    return session.get("joined_code") == state["join_code"]


def get_question_or_404(question_id):
    question = questions.get(question_id)
    if question is None:
        abort(404, description="That question doesn't exist. It may have been deleted.")
    return question


def voter_id():
    """Give each browser a random id so it can only vote once per question."""
    if "voter_id" not in session:
        session["voter_id"] = secrets.token_hex(16)
    return session["voter_id"]


def question_status(question):
    if question["id"] == state["current_id"]:
        return "live" if question["open"] else "closed"
    return "waiting" if question["open"] else "done"


def question_to_json(question):
    total = sum(question["votes"])
    return {
        "id": question["id"],
        "text": question["text"],
        "open": question["open"],
        "number": question_order.index(question["id"]) + 1,
        "count": len(question_order),
        "total": total,
        "options": [
            {
                "text": text,
                "votes": votes,
                "percent": round(votes * 100 / total) if total else 0,
            }
            for text, votes in zip(question["options"], question["votes"])
        ],
    }


@app.context_processor
def inject_globals():
    return {"site_address": site_address(), "join_code": state["join_code"]}


# --- Pages ---

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/teacher")
def teacher():
    return render_teacher_page()


def render_teacher_page(form=None, error=None, status=200):
    form = form or {"text": "", "options": ["", "", "", ""]}
    with lock:
        question_list = [
            {**questions[qid], "number": n, "status": question_status(questions[qid])}
            for n, qid in enumerate(question_order, start=1)
        ]
        current = questions.get(state["current_id"])
    return render_template(
        "teacher.html",
        questions=question_list,
        current=current,
        form=form,
        error=error,
        max_options=MAX_OPTIONS,
        max_question_length=MAX_QUESTION_LENGTH,
        max_option_length=MAX_OPTION_LENGTH,
    ), status


@app.route("/projector")
def projector():
    return render_template("projector.html")


@app.route("/vote")
def vote():
    if not has_joined():
        return render_template("join.html", code="", error=None)
    voter_id()
    return render_template("vote.html")


@app.post("/join")
def join():
    code = request.form.get("code", "").strip()
    error = None
    if not (len(code) == 4 and code.isdigit()):
        error = "The class code is 4 digits. Check the projector and try again."
    elif code != state["join_code"]:
        error = "That code doesn't match. Check the projector and try again."

    if error:
        return render_template("join.html", code=code, error=error), 400

    session["joined_code"] = code
    voter_id()
    return redirect(url_for("vote"))


# --- Teacher actions ---

@app.post("/teacher/questions")
def create_question():
    text = request.form.get("text", "").strip()
    options = [o.strip() for o in request.form.getlist("options")]
    filled = [o for o in options if o]
    form = {"text": text, "options": options or ["", ""]}

    error = None
    if not text and not filled:
        error = f"The form is empty. Type a question and at least {MIN_OPTIONS} answer options."
    elif not text:
        error = "Please type a question. The question box is empty."
    elif len(text) > MAX_QUESTION_LENGTH:
        error = f"The question is too long (max {MAX_QUESTION_LENGTH} characters)."
    elif len(filled) < MIN_OPTIONS:
        filled_text = "no answer options" if not filled else "only 1 answer option"
        error = (
            f"You filled in {filled_text}. "
            f"A question needs at least {MIN_OPTIONS} so students have a choice."
        )
    elif len(filled) > MAX_OPTIONS:
        error = f"A question can have at most {MAX_OPTIONS} answer options."
    elif any(len(o) > MAX_OPTION_LENGTH for o in filled):
        error = f"Each answer option must be at most {MAX_OPTION_LENGTH} characters."
    elif len({o.lower() for o in filled}) != len(filled):
        error = "Two answer options are the same. Please make each one different."

    if error:
        return render_teacher_page(form=form, error=error, status=400)

    with lock:
        question_id = next(next_question_id)
        questions[question_id] = {
            "id": question_id,
            "text": text,
            "options": filled,
            "votes": [0] * len(filled),
            "voters": set(),
            "open": True,
        }
        question_order.append(question_id)
        # The first question goes straight onto the projector.
        if state["current_id"] is None:
            state["current_id"] = question_id
            flash("Question added and now showing on the projector.", "success")
        else:
            flash("Question added to the queue.", "success")
    return redirect(url_for("teacher"))


@app.post("/teacher/questions/<int:question_id>/show")
def show_question(question_id):
    with lock:
        question = get_question_or_404(question_id)
        state["current_id"] = question_id
    flash(f"Now showing: “{question['text']}”", "success")
    return redirect(url_for("teacher"))


@app.post("/teacher/questions/<int:question_id>/toggle")
def toggle_question(question_id):
    with lock:
        question = get_question_or_404(question_id)
        question["open"] = not question["open"]
    flash("Voting reopened." if question["open"] else "Voting closed.", "success")
    return redirect(url_for("teacher"))


@app.post("/teacher/questions/<int:question_id>/reset")
def reset_question(question_id):
    with lock:
        question = get_question_or_404(question_id)
        question["votes"] = [0] * len(question["options"])
        question["voters"] = set()
    flash("Votes cleared for that question.", "success")
    return redirect(url_for("teacher"))


@app.post("/teacher/questions/<int:question_id>/delete")
def delete_question(question_id):
    with lock:
        get_question_or_404(question_id)
        del questions[question_id]
        question_order.remove(question_id)
        if state["current_id"] == question_id:
            state["current_id"] = None
    flash("Question deleted.", "success")
    return redirect(url_for("teacher"))


@app.post("/teacher/next")
def next_question():
    with lock:
        if not question_order:
            flash("There are no questions yet. Add one first.", "error")
            return redirect(url_for("teacher"))

        current_id = state["current_id"]
        if current_id is None:
            new_id = question_order[0]
        else:
            position = question_order.index(current_id)
            if position + 1 >= len(question_order):
                flash("That was the last question. Add another one to keep going.", "error")
                return redirect(url_for("teacher"))
            # Close the question we're leaving so late votes don't sneak in.
            questions[current_id]["open"] = False
            new_id = question_order[position + 1]

        state["current_id"] = new_id
        text = questions[new_id]["text"]
    flash(f"Now showing: “{text}”", "success")
    return redirect(url_for("teacher"))


@app.post("/teacher/new-code")
def new_code():
    with lock:
        state["join_code"] = new_join_code()
    flash(f"New class code: {state['join_code']}. Students will need to enter it again.", "success")
    return redirect(url_for("teacher"))


@app.post("/teacher/clear")
def clear_projector():
    with lock:
        state["current_id"] = None
    flash("The projector is now showing the waiting screen.", "success")
    return redirect(url_for("teacher"))


# --- JSON API used by the polling JavaScript ---

@app.get("/api/current")
def api_current():
    with lock:
        question = questions.get(state["current_id"])
        # join_code is included so the projector can show a new code without a reload.
        if question is None:
            return jsonify(
                question=None, has_voted=False, joined=has_joined(), join_code=state["join_code"],
            )
        return jsonify(
            question=question_to_json(question),
            has_voted=session.get("voter_id") in question["voters"],
            joined=has_joined(),
            join_code=state["join_code"],
        )


def is_whole_number(value):
    # bool is a subclass of int in Python, so rule it out explicitly.
    return isinstance(value, int) and not isinstance(value, bool)


@app.post("/api/vote")
def api_vote():
    data = request.get_json(silent=True)
    if (
        not isinstance(data, dict)
        or not is_whole_number(data.get("question_id"))
        or not is_whole_number(data.get("option"))
    ):
        return api_error("Your vote couldn't be read. Please refresh the page and try again.", 400)
    if not has_joined():
        return api_error("Please enter the class code first.", 403)

    voter = voter_id()
    with lock:
        question = questions.get(data["question_id"])
        if question is None:
            return api_error(
                "That question doesn't exist. It may have been deleted. Showing the current one now.",
                404,
            )
        if question["id"] != state["current_id"]:
            return api_error("This question is no longer active. Showing the current one now.", 409)
        if not question["open"]:
            return api_error("Voting is closed for this question.", 409)
        if not 0 <= data["option"] < len(question["options"]):
            return api_error(
                f"That answer option doesn't exist. Please pick one of the "
                f"{len(question['options'])} options shown.",
                400,
            )
        if voter in question["voters"]:
            return api_error("You've already voted on this question.", 409)

        question["votes"][data["option"]] += 1
        question["voters"].add(voter)
    return jsonify(ok=True)


def api_error(message, status):
    return jsonify(error=message), status


# --- Error handling: never show a traceback, always a clear message ---

@app.errorhandler(HTTPException)
def handle_http_error(error):
    messages = {
        400: "The request didn't make sense. Please go back and try again.",
        404: "That page doesn't exist. Check the address or go back home.",
        405: "That action isn't allowed on this page.",
    }
    # Use our own message when the code passed one to abort(), else a friendly default.
    if error.description != type(error).description:
        message = error.description
    else:
        message = messages.get(error.code, "Something went wrong with that request.")

    if request.path.startswith("/api/"):
        return api_error(message, error.code)
    if error.code == 404:
        return render_error_page("404.html", 404, message)
    if error.code == 500:
        return render_error_page("500.html", 500, message)
    return render_error_page("error.html", error.code, message)


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    # Log the full traceback in the terminal for us; the browser only gets a friendly page.
    app.logger.exception("Unexpected error")
    message = "Something went wrong on the server. Please try again."
    if request.path.startswith("/api/"):
        return api_error(message, 500)
    return render_error_page("500.html", 500, message)


def render_error_page(template, code, message):
    try:
        return render_template(template, code=code, message=message), code
    except Exception:
        # If even the error page fails to render, fall back to plain HTML rather than a traceback.
        app.logger.exception("Error page failed to render")
        return (
            f"<!doctype html><title>Error {code}</title>"
            f"<h1>Error {code}</h1><p>Something went wrong. Please go back and try again.</p>"
            f'<p><a href="/">Back to home</a></p>',
            code,
        )


# Never run with the debugger, even if FLASK_DEBUG=1 or `flask run --debug` is used:
# the debugger shows tracebacks in the browser.
app.config["DEBUG"] = False
app.config["PROPAGATE_EXCEPTIONS"] = False


if __name__ == "__main__":
    print(f"\n  Teacher:  http://127.0.0.1:{PORT}/teacher")
    print(f"  Students: go to {site_address()} and enter code {state['join_code']}\n")
    # 0.0.0.0 lets students' phones on the same Wi-Fi reach the app.
    app.run(host="0.0.0.0", port=PORT, debug=False)
