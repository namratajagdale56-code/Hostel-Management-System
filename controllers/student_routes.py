from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database.db import mongo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson import ObjectId
import os

student = Blueprint(
    "student",
    __name__,
    url_prefix="/student",
    template_folder="../templates/student"
)

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ------------------------------- Helpers ---------------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required():
    if "student_id" not in session:
        flash("Please login first!", "danger")
        return False
    return True


# ========================== REGISTER ==============================
@student.route("/register", methods=["GET", "POST"])
def register():

    db = mongo.cx["hosteler"]

    if request.method == "POST":

        full_name = request.form.get("full_name")
        prn = request.form.get("prn")
        password = request.form.get("password")

        if not full_name or not prn or not password:
            flash("Full Name, PRN & Password are required!", "danger")
            return redirect(url_for("student.register"))

        # PRN Check
        if db.hostel_data.find_one({"prn": prn}):
            flash("PRN already exists!", "danger")
            return redirect(url_for("student.register"))

        # PHOTO
        photo = request.files.get("photo")
        filename = "default.png"

        if photo and allowed_file(photo.filename):
            filename = secure_filename(photo.filename)
            photo.save(os.path.join(UPLOAD_FOLDER, filename))

        # SAVE DATA
        student_data = {
            "full_name": full_name,
            "prn": prn,
            "department": request.form.get("department"),
            "year": request.form.get("year"),
            "email": request.form.get("email"),
            "mobile": request.form.get("mobile"),
            "parent_contact": request.form.get("parent_contact"),
            "aadhar": request.form.get("aadhar"),
            "address": request.form.get("address"),

            # default empty room
            "room_no": "",
            "room_block": "",
            "room_floor": "",

            "photo": filename,
            "password": generate_password_hash(password)
        }

        db.hostel_data.insert_one(student_data)

        flash("Registration Successful!", "success")
        return redirect(url_for("student.login"))

    return render_template("register.html")


# ========================== LOGIN ==============================
@student.route("/login", methods=["GET", "POST"])
def login():

    db = mongo.cx["hosteler"]

    if request.method == "POST":

        prn = request.form.get("prn")
        password = request.form.get("password")

        student_data = db.hostel_data.find_one({"prn": prn})

        if not student_data:
            flash("PRN not found!", "danger")
            return redirect(url_for("student.login"))

        if not check_password_hash(student_data["password"], password):
            flash("Incorrect Password!", "danger")
            return redirect(url_for("student.login"))

        # SESSION
        session["student_id"] = str(student_data["_id"])
        session["student_prn"] = student_data["prn"]
        session["student_name"] = student_data["full_name"]
        session["role"] = "student"

        return redirect(url_for("student.dashboard"))

    return render_template("login.html")


# ========================== DASHBOARD ==============================
@student.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("student.login"))

    return render_template("dashboard.html", student_name=session.get("student_name"))


# ========================== PROFILE ==============================
@student.route("/my-profile")
def my_profile():
    if not login_required():
        return redirect(url_for("student.login"))

    db = mongo.cx["hosteler"]
    student_data = db.hostel_data.find_one({"_id": ObjectId(session["student_id"])})

    return render_template("my_profile.html", student=student_data)


# ========================== ROOM STATUS ==============================
@student.route("/room-status")
def room_status():

    if not login_required():
        return redirect(url_for("student.login"))

    db = mongo.cx["hosteler"]
    student_data = db.hostel_data.find_one({"_id": ObjectId(session["student_id"])})

    room = None
    if student_data.get("room_no"):
        room = db.rooms.find_one({"room_no": student_data["room_no"]})

    return render_template("room_status.html", student=student_data, room=room)


# ========================== ALL ROOMS ==============================
@student.route("/all-rooms")
def all_rooms():

    if not login_required():
        return redirect(url_for("student.login"))

    db = mongo.cx["hosteler"]
    all_rooms = list(db.rooms.find())

    student_data = db.hostel_data.find_one({"_id": ObjectId(session["student_id"])})
    assigned = None

    if student_data.get("room_no"):
        assigned = db.rooms.find_one({"room_no": student_data["room_no"]})

    return render_template("all_room_status.html",
                           assigned_room=assigned,
                           all_rooms=all_rooms)


# ========================== FEES ==============================
@student.route("/fee-status")
def fee_status():
    if not login_required():
        return redirect(url_for("student.login"))

    db = mongo.cx["hosteler"]
    fees = list(db.fees.find({"student_prn": session["student_prn"]}))

    return render_template("fee_status.html", fees=fees)


# ========================== LEAVE FORM ==============================
@student.route("/leave-form", methods=["GET", "POST"])
def leave_form():

    if not login_required():
        return redirect(url_for("student.login"))

    db = mongo.cx["hosteler"]

    if request.method == "POST":

        if not request.form["reason"]:
            flash("Please enter a valid reason!", "danger")
            return redirect(url_for("student.leave_form"))

        leave_data = {
            "student_id": session["student_id"],
            "student_name": session["student_name"],
            "prn": session["student_prn"],
            "from_date": request.form["from_date"],
            "to_date": request.form["to_date"],
            "reason": request.form["reason"],
            "status": "Pending"
        }

        db.leave_requests.insert_one(leave_data)

        flash("Leave Request Submitted!", "success")
        return redirect(url_for("student.leave_status"))

    return render_template("leave_form.html")


# ========================== LEAVE STATUS ==============================
@student.route("/leave-status")
def leave_status():

    if not login_required():
        return redirect(url_for("student.login"))

    db = mongo.cx["hosteler"]
    leaves = list(db.leave_requests.find({"student_id": session["student_id"]}))

    return render_template("leave_status.html", leaves=leaves)


# ========================== COMPLAINT FORM ==============================
@student.route("/complaint-form", methods=["GET", "POST"])
def complaint_form():

    if not login_required():
        return redirect(url_for("student.login"))

    db = mongo.cx["hosteler"]

    if request.method == "POST":

        subject = request.form["subject"]
        message = request.form["message"]

        if not subject or not message:
            flash("Please fill all fields!", "danger")
            return redirect(url_for("student.complaint_form"))

        complaint = {
            "student_id": session["student_id"],
            "student_name": session["student_name"],
            "prn": session["student_prn"],
            "subject": subject,
            "message": message,
            "admin_reply": "",
            "status": "Pending"
        }

        db.complaints.insert_one(complaint)
        flash("Complaint Submitted!", "success")
        return redirect(url_for("student.complaint_status"))

    return render_template("complaint_form.html")


# ========================== COMPLAINT STATUS ==============================
@student.route("/complaint-status")
def complaint_status():

    if not login_required():
        return redirect(url_for("student.login"))

    db = mongo.cx["hosteler"]
    complaints = list(db.complaints.find({"student_id": session["student_id"]}))

    return render_template("complaint_status.html", complaints=complaints)


# ========================== LOGOUT ==============================
@student.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect(url_for("student.login"))
