from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import json
import os

app = Flask(__name__)
app.secret_key = "welearn_secret_2024"

if os.environ.get("FIREBASE_CREDENTIALS"):
    cred = credentials.Certificate(json.loads(os.environ["FIREBASE_CREDENTIALS"]))
else:
    cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ======= АВТОРИЗАЦІЯ =======

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        users_ref = db.collection("users").where("username", "==", username).where("password", "==", password).stream()
        user = None
        for u in users_ref:
            user = u.to_dict()
            user["id"] = u.id
        if user:
            session["user"] = user["username"]
            session["role"] = user["role"]
            session["user_id"] = user["id"]
            if user["role"] == "admin":
                return redirect(url_for("admin"))
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Невірний логін або пароль")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ======= ВЧИТЕЛЬ =======

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    groups_ref = db.collection("groups").stream()
    groups = [{"id": g.id, **g.to_dict()} for g in groups_ref]
    return render_template("dashboard.html", groups=groups, user=session["user"])

@app.route("/group/<group_id>")
def group(group_id):
    if "user" not in session:
        return redirect(url_for("login"))
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    group_ref = db.collection("groups").document(group_id).get()
    group = {"id": group_ref.id, **group_ref.to_dict()}
    students_ref = db.collection("groups").document(group_id).collection("students").stream()
    students = [{"id": s.id, **s.to_dict()} for s in students_ref]
    grades_ref = db.collection("grades").where("group_id", "==", group_id).where("month", "==", month).stream()
    grades = {}
    for g in grades_ref:
        d = g.to_dict()
        grades[d["student_id"]] = d
    columns_ref = db.collection("columns").where("group_id", "==", group_id).where("month", "==", month).stream()
    columns = [{"id": c.id, **c.to_dict()} for c in columns_ref]
    if not columns:
        for i in range(1, 9):
            db.collection("columns").add({"group_id": group_id, "month": month, "name": f"Заняття {i}", "order": i, "type": "lesson"})
        db.collection("columns").add({"group_id": group_id, "month": month, "name": "Тест місяця", "order": 99, "type": "test", "max_score": 100})
        columns_ref = db.collection("columns").where("group_id", "==", group_id).where("month", "==", month).stream()
        columns = [{"id": c.id, **c.to_dict()} for c in columns_ref]
    columns.sort(key=lambda x: x.get("order", 0))
    groups_ref = db.collection("groups").stream()
    groups = [{"id": g.id, **g.to_dict()} for g in groups_ref]
    return render_template("group.html", group=group, students=students, grades=grades, columns=columns, month=month, groups=groups, user=session["user"])

@app.route("/save_grade", methods=["POST"])
def save_grade():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    group_id = data["group_id"]
    student_id = data["student_id"]
    month = data["month"]
    column_id = data["column_id"]
    value = data["value"]
    comment = data.get("comment", "")
    grades_ref = db.collection("grades").where("group_id", "==", group_id).where("student_id", "==", student_id).where("month", "==", month).stream()
    grade_doc = None
    for g in grades_ref:
        grade_doc = g
    if grade_doc:
        existing = grade_doc.to_dict()
        scores = existing.get("scores", {})
        scores[column_id] = {"value": value, "comment": comment}
        db.collection("grades").document(grade_doc.id).update({"scores": scores})
    else:
        db.collection("grades").add({"group_id": group_id, "student_id": student_id, "month": month, "scores": {column_id: {"value": value, "comment": comment}}})
    return jsonify({"success": True})

@app.route("/add_student", methods=["POST"])
def add_student():
    if "user" not in session:
        return redirect(url_for("login"))
    group_id = request.form["group_id"]
    name = request.form["name"]
    parent_code = request.form["parent_code"]
    db.collection("groups").document(group_id).collection("students").add({"name": name, "parent_code": parent_code})
    return redirect(url_for("group", group_id=group_id))

@app.route("/add_group", methods=["POST"])
def add_group():
    if "user" not in session:
        return redirect(url_for("login"))
    name = request.form["name"]
    db.collection("groups").add({"name": name})
    return redirect(url_for("dashboard"))

@app.route("/rename_group", methods=["POST"])
def rename_group():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    db.collection("groups").document(data["group_id"]).update({"name": data["name"]})
    return jsonify({"success": True})

@app.route("/rename_student", methods=["POST"])
def rename_student():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    db.collection("groups").document(data["group_id"]).collection("students").document(data["student_id"]).update({"name": data["name"]})
    return jsonify({"success": True})

@app.route("/delete_student", methods=["POST"])
def delete_student():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    db.collection("groups").document(data["group_id"]).collection("students").document(data["student_id"]).delete()
    return jsonify({"success": True})

@app.route("/delete_group", methods=["POST"])
def delete_group():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    db.collection("groups").document(data["group_id"]).delete()
    return jsonify({"success": True})

@app.route("/add_column", methods=["POST"])
def add_column():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    col_type = data.get("col_type", "lesson")
    col_data = {"group_id": data["group_id"], "month": data["month"], "name": data["name"], "order": data["order"], "type": col_type}
    if col_type == "test":
        col_data["max_score"] = data.get("max_score", 100)
    db.collection("columns").add(col_data)
    return jsonify({"success": True})

@app.route("/rename_column", methods=["POST"])
def rename_column():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    update_data = {"name": data["name"]}
    if "max_score" in data:
        update_data["max_score"] = data["max_score"]
    db.collection("columns").document(data["column_id"]).update(update_data)
    return jsonify({"success": True})

def calc_scores(columns, scores):
    lesson_scores = []
    test_converted = []
    test_info = []
    for col in columns:
        val = scores.get(col["id"], {}).get("value", "")
        if val and val != "нб":
            try:
                num = float(val)
            except:
                continue
            if col.get("type") == "test":
                max_score = col.get("max_score") or 100
                converted = round(num / max_score * 12, 1)
                test_converted.append(converted)
                test_info.append({"name": col.get("name"), "value": num, "max": max_score})
            else:
                lesson_scores.append(num)
    all_scores = lesson_scores + test_converted
    avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0
    return avg, test_info

MONTHS_ORDER = ['2026-01','2026-02','2026-03','2026-04','2026-05','2026-06','2026-07','2026-08','2026-09','2026-10','2026-11','2026-12']
MONTH_NAMES_SHORT = {'01':'Січ','02':'Лют','03':'Бер','04':'Кві','05':'Тра','06':'Чер','07':'Лип','08':'Сер','09':'Вер','10':'Жов','11':'Лис','12':'Гру'}

def get_student_progress(group_id, student_id):
    progress = []
    for m in MONTHS_ORDER:
        columns_ref = db.collection("columns").where("group_id", "==", group_id).where("month", "==", m).stream()
        columns = [{"id": c.id, **c.to_dict()} for c in columns_ref]
        if not columns:
            continue
        grades_ref = db.collection("grades").where("group_id", "==", group_id).where("student_id", "==", student_id).where("month", "==", m).stream()
        scores = {}
        has_data = False
        for g in grades_ref:
            scores = g.to_dict().get("scores", {})
            has_data = True
        if not has_data:
            continue
        avg, _ = calc_scores(columns, scores)
        year, month_num = m.split('-')
        label = MONTH_NAMES_SHORT[month_num] + ' ' + year[2:]
        progress.append({"month": m, "label": label, "avg": avg})
    return progress

@app.route("/rating/<group_id>")
def rating(group_id):
    if "user" not in session:
        return redirect(url_for("login"))
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    group_ref = db.collection("groups").document(group_id).get()
    group = {"id": group_ref.id, **group_ref.to_dict()}
    students_ref = db.collection("groups").document(group_id).collection("students").stream()
    students = [{"id": s.id, **s.to_dict()} for s in students_ref]
    columns_ref = db.collection("columns").where("group_id", "==", group_id).where("month", "==", month).stream()
    columns = [{"id": c.id, **c.to_dict()} for c in columns_ref]
    grades_ref = db.collection("grades").where("group_id", "==", group_id).where("month", "==", month).stream()
    grades = {}
    for g in grades_ref:
        d = g.to_dict()
        grades[d["student_id"]] = d
    rating_list = []
    for student in students:
        sid = student["id"]
        scores = grades.get(sid, {}).get("scores", {})
        avg, test_info = calc_scores(columns, scores)
        rating_list.append({"student": student, "avg": avg, "tests": test_info})
    rating_list.sort(key=lambda x: x["avg"], reverse=True)
    for i, item in enumerate(rating_list):
        item["rank"] = i + 1
    groups_ref = db.collection("groups").stream()
    groups = [{"id": g.id, **g.to_dict()} for g in groups_ref]
    return render_template("rating.html", group=group, rating=rating_list, month=month, groups=groups, user=session["user"])

@app.route("/progress/<group_id>")
def progress_page(group_id):
    if "user" not in session:
        return redirect(url_for("login"))
    group_ref = db.collection("groups").document(group_id).get()
    group = {"id": group_ref.id, **group_ref.to_dict()}
    students_ref = db.collection("groups").document(group_id).collection("students").stream()
    students = [{"id": s.id, **s.to_dict()} for s in students_ref]
    selected_id = request.args.get("student_id")
    if not selected_id and students:
        selected_id = students[0]["id"]
    progress_data = get_student_progress(group_id, selected_id) if selected_id else []
    groups_ref = db.collection("groups").stream()
    groups = [{"id": g.id, **g.to_dict()} for g in groups_ref]
    return render_template("progress.html", group=group, students=students, selected_id=selected_id, progress=progress_data, groups=groups, user=session["user"])

# ======= БАТЬКИ =======

from flask import send_from_directory

@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")
@app.route("/parent", methods=["GET", "POST"])
def parent():
    if request.method == "POST":
        code = request.form["code"]
        groups_ref = db.collection("groups").stream()
        for group in groups_ref:
            students_ref = db.collection("groups").document(group.id).collection("students").where("parent_code", "==", code).stream()
            for student in students_ref:
                s = student.to_dict()
                s["id"] = student.id
                s["group_id"] = group.id
                session["parent_student"] = s
                return redirect(url_for("parent_dashboard"))
        return render_template("parent_login.html", error="Невірний код")
    return render_template("parent_login.html")

@app.route("/parent/dashboard")
def parent_dashboard():
    if "parent_student" not in session:
        return redirect(url_for("parent"))
    student = session["parent_student"]
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    grades_ref = db.collection("grades").where("group_id", "==", student["group_id"]).where("student_id", "==", student["id"]).where("month", "==", month).stream()
    grades = {}
    for g in grades_ref:
        grades = g.to_dict().get("scores", {})
    columns_ref = db.collection("columns").where("group_id", "==", student["group_id"]).where("month", "==", month).stream()
    columns = [{"id": c.id, **c.to_dict()} for c in columns_ref]
    columns.sort(key=lambda x: x.get("order", 0))
    rating_data = None
    students_ref2 = db.collection("groups").document(student["group_id"]).collection("students").stream()
    all_students = [{"id": s.id, **s.to_dict()} for s in students_ref2]
    all_grades_ref = db.collection("grades").where("group_id", "==", student["group_id"]).where("month", "==", month).stream()
    all_grades = {}
    for g in all_grades_ref:
        d = g.to_dict()
        all_grades[d["student_id"]] = d
    avgs = []
    for s in all_students:
        sg = all_grades.get(s["id"], {}).get("scores", {})
        avg, _ = calc_scores(columns, sg)
        avgs.append({"id": s["id"], "avg": avg})
    avgs.sort(key=lambda x: x["avg"], reverse=True)
    for i, a in enumerate(avgs):
        if a["id"] == student["id"]:
            rating_data = {"rank": i + 1, "total": len(avgs)}
    own_avg, _ = calc_scores(columns, grades)
    progress_data = get_student_progress(student["group_id"], student["id"])
    return render_template("parent_dashboard.html", student=student, grades=grades, columns=columns, month=month, rating=rating_data, avg=own_avg, progress=progress_data)

# ======= АДМІН =======

@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    users_ref = db.collection("users").stream()
    users = [{"id": u.id, **u.to_dict()} for u in users_ref]
    return render_template("admin.html", users=users)

@app.route("/admin/add_user", methods=["POST"])
def add_user():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    username = request.form["username"]
    password = request.form["password"]
    role = request.form["role"]
    db.collection("users").add({"username": username, "password": password, "role": role})
    return redirect(url_for("admin"))

@app.route("/admin/delete_user", methods=["POST"])
def delete_user():
    if session.get("role") != "admin":
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    db.collection("users").document(data["user_id"]).delete()
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(debug=True)