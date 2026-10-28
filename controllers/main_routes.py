# controllers/main_routes.py
from flask import (
    Blueprint, render_template, redirect, url_for, request, session, flash,
    current_app
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from database.db import mongo
import os
import time
import logging

main = Blueprint("main", __name__)

# ----- logger -----
logger = logging.getLogger(__name__)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)

# Allowed image extensions for optional photo upload
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_upload_file(file_obj, prefix="file", dest_subfolder="uploads"):
    """
    Save uploaded file into static/<dest_subfolder> and return stored filename (or empty string).
    By default it saves to static/uploads for student photos, but team uploads can use dest_subfolder='image'.
    """
    if not file_obj or not getattr(file_obj, "filename", ""):
        return ""
    filename = secure_filename(file_obj.filename)
    if not allowed_file(filename):
        return ""
    uploads_dir = os.path.join(current_app.static_folder, dest_subfolder)
    os.makedirs(uploads_dir, exist_ok=True)
    ts = int(time.time())
    filename = f"{prefix}_{ts}_{filename}"
    save_path = os.path.join(uploads_dir, filename)
    file_obj.save(save_path)
    return filename


# ---------------- STATIC PAGES ----------------
@main.route("/")
def home():
    return render_template("index.html")


@main.route("/about")
def about():
    """
    Build team_entries list of dicts for the template.
    Each dict: {"img": filename_or_None, "name": str, "role": str, "phone": str_or_empty}
    """
    image_dir = os.path.join(current_app.static_folder, "image")
    available = set()
    try:
        if os.path.isdir(image_dir):
            for fname in os.listdir(image_dir):
                low = fname.lower()
                if low.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    available.add(fname)
    except Exception:
        logger.exception("Failed to list static/image directory")

    def find_fname(*keywords):
        """Return first filename in available that contains any of the keywords (order-independent)."""
        for kw in keywords:
            for fname in available:
                if kw in fname.lower():
                    return fname
        return None

    # try to locate specific people by common filename substrings
    sonali = find_fname("sonali")
    kapse = find_fname("kapse", "kapase", "sarita")
    bharti = find_fname("bharti", "bharati")

    # TODO: Replace these numbers with real contact numbers
    team_entries = [
        {"img": sonali, "name": "Mrs. Sonali Suryawanshi", "role": "Warden", "phone": "9876543210"},
        {"img": kapse,  "name": "Mrs. Sarita Kapase",     "role": "Rector", "phone": "9876501234"},
        {"img": bharti, "name": "Mrs. Bharati Patil",     "role": "Rector", "phone": "9876512345"},
    ]

    logger.info("team_entries => %r", team_entries)
    logger.info("available images => %r", sorted(list(available)))

    return render_template(
        "about.html",
        team_entries=team_entries,
        team_images=sorted(list(available))
    )


@main.route("/contact")
def contact():
    return render_template("contact.html")


@main.route("/gallery")
def gallery():
    return render_template("gallery.html")


# ---------------- UPLOAD TEAM PHOTO (simple form) ----------------
@main.route("/upload-team-photo", methods=["GET", "POST"])
def upload_team_photo():
    """
    Simple upload form — choose a file and a target name (eg. sonali.jpg).
    Saves to <project_root>/static/image/<target_filename>
    If POST without a custom target name, it will save with a timestamped secure filename.
    """
    if request.method == "POST":
        target_name = (request.form.get("target_name") or "").strip()
        f = request.files.get("photo")
        if not f or f.filename == "":
            flash("No file selected", "danger")
            return redirect(request.url)

        # Validate uploaded file extension
        if not allowed_file(f.filename):
            flash("File type not allowed. Use png/jpg/jpeg/gif/webp", "danger")
            return redirect(request.url)

        # If user supplied a target_name, ensure it has valid extension and save with that name
        if target_name:
            if "." not in target_name or target_name.rsplit(".", 1)[1].lower() not in ALLOWED_EXT:
                flash("Target filename must end with a valid extension (jpg/png/...)", "danger")
                return redirect(request.url)
            filename = secure_filename(target_name)
            save_dir = os.path.join(current_app.static_folder, "image")
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, filename)
            try:
                f.save(save_path)
                flash(f"Saved as image/{filename}", "success")
                logger.info("Saved team photo as static/image/%s", filename)
            except Exception:
                logger.exception("Failed to save team photo to static/image/")
                flash("Failed to save file. Try again.", "danger")
            return redirect(url_for("main.upload_team_photo"))

        # Otherwise, save with generated name into static/image
        try:
            saved_name = save_upload_file(f, prefix="team", dest_subfolder="image")
            if saved_name:
                flash(f"Saved as image/{saved_name}", "success")
                logger.info("Saved team photo as static/image/%s", saved_name)
            else:
                flash("Could not save file (invalid?).", "danger")
        except Exception:
            logger.exception("Error while saving team photo")
            flash("Failed to save file. Try again.", "danger")

        return redirect(url_for("main.upload_team_photo"))

    return render_template("upload_team_photo.html")


# ---------------- STUDENT REGISTER ----------------
@main.route("/register", methods=["GET", "POST"])
def register():
    """
    Robust registration route:
    - reads form (supports both `full_name` and `fullname`)
    - supports `room_no` or `room` form fields
    - optional photo upload (saved to static/uploads)
    - inserts document into hosteler.hostel_data
    """
    db = mongo.cx["hosteler"]

    if request.method == "POST":
        logger.info("POST /register - form keys: %s | files keys: %s",
                    list(request.form.keys()), list(request.files.keys()))

        full_name = request.form.get("full_name") or request.form.get("fullname") or ""
        full_name = full_name.strip()
        prn = (request.form.get("prn") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        department = (request.form.get("department") or "").strip()
        year = (request.form.get("year") or "").strip()
        mobile = (request.form.get("mobile") or "").strip()
        parent_contact = (request.form.get("parent_contact") or "").strip()
        aadhar = (request.form.get("aadhar") or "").strip()
        address = (request.form.get("address") or "").strip()
        room_no = (request.form.get("room_no") or request.form.get("room") or "").strip()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""

        if not full_name or not prn or not password:
            flash("Please fill required fields: Full Name, PRN and Password.", "danger")
            logger.info("Register failed: missing required (full_name=%s prn=%s pw=%s)",
                        bool(full_name), bool(prn), bool(password))
            return redirect(url_for("main.register"))

        if password != confirm_password:
            flash("Password and Confirm Password do not match.", "danger")
            logger.info("Register failed: password mismatch for PRN %s", prn)
            return redirect(url_for("main.register"))

        try:
            if db["hostel_data"].find_one({"prn": prn}):
                flash("PRN already exists!", "danger")
                logger.info("Register failed: duplicate PRN %s", prn)
                return redirect(url_for("main.register"))
        except Exception:
            logger.exception("DB error while checking duplicate PRN")
            flash("Database error. Please try again later.", "danger")
            return redirect(url_for("main.register"))

        if email:
            try:
                if db["hostel_data"].find_one({"email": email}):
                    flash("Email already registered!", "danger")
                    return redirect(url_for("main.register"))
            except Exception:
                logger.exception("Email-check error (ignored)")

        # ------------------------------
        # Optional: handle uploaded photo
        # ------------------------------
        photo_filename = ""
        photo = request.files.get("photo")
        if photo and getattr(photo, "filename", ""):
            try:
                # saves into static/uploads so templates that expect uploads path work
                photo_filename = save_upload_file(photo, prefix=prn or "student", dest_subfolder="uploads")
                logger.info("Saved uploaded photo: %s", photo_filename)

                # debug: log whether file exists on disk (optional)
                saved_path = os.path.join(current_app.static_folder, "uploads", photo_filename) if photo_filename else None
                if saved_path:
                    logger.info("Upload saved to: %s | exists=%s", saved_path, os.path.exists(saved_path))
            except Exception:
                logger.exception("Failed to save uploaded photo; continuing without photo")
                photo_filename = ""

        student_doc = {
            "full_name": full_name,
            "prn": prn,
            "email": email,
            "department": department,
            "year": year,
            "mobile": mobile,
            "parent_contact": parent_contact,
            "aadhar": aadhar,
            "address": address,
            "room_no": room_no,
            "room_block": "",
            "room_floor": "",
            "password": generate_password_hash(password),
            "photo": photo_filename
        }

        try:
            res = db["hostel_data"].insert_one(student_doc)
            logger.info("Inserted student id: %s (PRN=%s)", res.inserted_id, prn)
        except Exception:
            logger.exception("Failed to insert student document")
            flash("Registration failed (DB error). Try again.", "danger")
            return redirect(url_for("main.register"))

        flash("Registration successful! You can now login.", "success")
        return redirect(url_for("main.login"))

    return render_template("register.html")



# ---------------- LOGIN (ADMIN + STUDENT) ----------------
@main.route("/login", methods=["GET", "POST"])
def login():
    db = mongo.cx["hosteler"]

    if request.method == "POST":
        user_type = request.form.get("user_type")
        password = request.form.get("password", "")

        # ADMIN
        if user_type == "admin":
            email = (request.form.get("email") or "").lower().strip()
            admin = db["admin"].find_one({"email": email})
            if not admin:
                flash("Admin not found!", "danger")
                return redirect(url_for("main.login"))
            stored = admin.get("password", "")
            if stored and stored.startswith("pbkdf2:"):
                if not check_password_hash(stored, password):
                    flash("Incorrect admin password!", "danger")
                    return redirect(url_for("main.login"))
            else:
                if stored != password:
                    flash("Incorrect admin password!", "danger")
                    return redirect(url_for("main.login"))
            session.clear()
            session["role"] = "admin"
            session["admin_name"] = admin.get("name", "Admin")
            return redirect(url_for("admin.dashboard"))

        # STUDENT
        elif user_type == "student":
            prn = (request.form.get("prn") or "").strip()
            student = db["hostel_data"].find_one({"prn": prn})
            if not student:
                flash("PRN not found!", "danger")
                return redirect(url_for("main.login"))
            if not check_password_hash(student.get("password", ""), password):
                flash("Incorrect student password!", "danger")
                return redirect(url_for("main.login"))
            session.clear()
            session["role"] = "student"
            session["student_prn"] = student["prn"]
            session["student_name"] = student.get("full_name", "Student")
            return redirect(url_for("main.student_dashboard"))

        else:
            flash("Please select user type!", "warning")
            return redirect(url_for("main.login"))

    return render_template("login.html")


# ---------------- STUDENT DASHBOARD / PROFILE / OTHER ROUTES ----------------
@main.route("/student/dashboard")
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("main.login"))
    return render_template("student/dashboard.html", student_name=session.get("student_name"))


@main.route("/student/profile")
def student_profile():
    if session.get("role") != "student":
        return redirect(url_for("main.login"))
    student = mongo.cx["hosteler"]["hostel_data"].find_one({"prn": session.get("student_prn")})
    return render_template("student/my_profile.html", student=student)


@main.route("/student/fee_status")
def student_fee_status():
    if session.get("role") != "student":
        return redirect(url_for("main.login"))
    fees = list(mongo.cx["hosteler"]["fees"].find({"student_prn": session["student_prn"]}))
    return render_template("student/fee_status.html", fees=fees)


@main.route("/student/room_status")
def student_room_status():
    if session.get("role") != "student":
        return redirect(url_for("main.login"))
    db = mongo.cx["hosteler"]
    student = db["hostel_data"].find_one({"prn": session["student_prn"]})
    room_no = student.get("room_no")
    if not room_no:
        return render_template("student/room_status.html", room=None)
    room = db["rooms"].find_one({"room_no": room_no})
    return render_template("student/room_status.html", room=room)


@main.route("/student/all_rooms")
def student_all_rooms():
    if session.get("role") != "student":
        return redirect(url_for("main.login"))
    db = mongo.cx["hosteler"]
    student = db["hostel_data"].find_one({"prn": session["student_prn"]})
    assigned_room = None
    if student.get("room_no"):
        assigned_room = db["rooms"].find_one({"room_no": student["room_no"]})
    all_rooms = list(db["rooms"].find())
    return render_template("student/all_room_status.html", student=student, assigned_room=assigned_room, all_rooms=all_rooms)


@main.route("/student/leave_form", methods=["GET", "POST"])
def student_leave_form():
    if session.get("role") != "student":
        return redirect(url_for("main.login"))
    if request.method == "POST":
        leave_data = {
            "student_prn": session["student_prn"],
            "student_name": session["student_name"],
            "from_date": request.form["from_date"],
            "to_date": request.form["to_date"],
            "reason": request.form["reason"],
            "status": "Pending",
            "admin_reply": ""
        }
        mongo.cx["hosteler"]["leave_requests"].insert_one(leave_data)
        flash("Leave request submitted!", "success")
        return redirect(url_for("main.student_leave_status"))
    return render_template("student/leave_form.html")


@main.route("/student/leave_status")
def student_leave_status():
    if session.get("role") != "student":
        return redirect(url_for("main.login"))
    leaves = list(mongo.cx["hosteler"]["leave_requests"].find({"student_prn": session["student_prn"]}))
    return render_template("student/leave_status.html", leaves=leaves)


@main.route("/student/complaint_form", methods=["GET", "POST"])
def student_complaint_form():
    if session.get("role") != "student":
        return redirect(url_for("main.login"))
    if request.method == "POST":
        complaint = {
            "student_prn": session["student_prn"],
            "student_name": session["student_name"],
            "subject": request.form["subject"],
            "message": request.form["message"],
            "admin_reply": "",
            "status": "Pending"
        }
        mongo.cx["hosteler"]["complaints"].insert_one(complaint)
        flash("Complaint submitted!", "success")
        return redirect(url_for("main.student_complaint_status"))
    return render_template("student/complaint_form.html")


@main.route("/student/complaint_status")
def student_complaint_status():
    if session.get("role") != "student":
        return redirect(url_for("main.login"))
    complaints = list(mongo.cx["hosteler"]["complaints"].find({"student_prn": session["student_prn"]}))
    return render_template("student/complaint_status.html", complaints=complaints)


@main.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect(url_for("main.login"))
