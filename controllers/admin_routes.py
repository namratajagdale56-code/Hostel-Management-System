from flask import Blueprint, render_template, redirect, url_for, session, flash, request, send_file
from database.db import mongo
from bson import ObjectId
from werkzeug.security import check_password_hash
from io import BytesIO
import openpyxl
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import os

admin = Blueprint("admin", __name__, url_prefix="/admin")


# -------------------- CHECK ADMIN LOGIN --------------------
def admin_required():
    if session.get("role") != "admin":
        flash("Please login as Admin!", "danger")
        return False
    return True


# -------------------- ADMIN LOGIN --------------------
@admin.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = mongo.cx["hosteler"]
        admin_user = db["admin"].find_one({"username": username})

        if not admin_user:
            flash("Admin not found!", "danger")
            return redirect(url_for("admin.login"))

        if not check_password_hash(admin_user["password"], password):
            flash("Incorrect password!", "danger")
            return redirect(url_for("admin.login"))

        session.clear()
        session["role"] = "admin"
        session["admin_id"] = str(admin_user["_id"])

        return redirect(url_for("admin.dashboard"))

    return render_template("admin/admin_login.html")


# -------------------- DASHBOARD --------------------
@admin.route("/dashboard")
def dashboard():
    if not admin_required():
        return redirect(url_for("admin.login"))
    return render_template("admin/dashboard.html")


# -------------------- MANAGE STUDENTS --------------------
@admin.route("/students")
def manage_students():
    if not admin_required():
        return redirect(url_for("admin.login"))

    students = list(mongo.cx["hosteler"]["hostel_data"].find())
    return render_template("admin/manage_students.html", students=students)


@admin.route("/students/view/<id>")
def view_student(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    student = mongo.cx["hosteler"]["hostel_data"].find_one({"_id": ObjectId(id)})
    return render_template("admin/view_student.html", student=student)


@admin.route("/students/edit/<id>", methods=["GET", "POST"])
def edit_student(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    db = mongo.cx["hosteler"]
    student = db["hostel_data"].find_one({"_id": ObjectId(id)})

    if request.method == "POST":
        db["hostel_data"].update_one(
            {"_id": ObjectId(id)},
            {"$set": {
                "full_name": request.form["full_name"],
                "prn": request.form["prn"],
                "department": request.form["department"],
                "year": request.form["year"],
                "mobile": request.form["mobile"]
            }}
        )
        flash("Student updated!", "success")
        return redirect(url_for("admin.manage_students"))

    return render_template("admin/edit_student.html", student=student)


# -------------------- DELETE STUDENT --------------------
@admin.route("/students/delete/<id>")
def delete_student(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    db = mongo.cx["hosteler"]

    student = db["hostel_data"].find_one({"_id": ObjectId(id)})
    if student and student.get("room_no"):
        db["rooms"].update_one(
            {"room_no": student["room_no"]},
            {"$inc": {"occupied": -1, "available_beds": 1}}
        )

    db["hostel_data"].delete_one({"_id": ObjectId(id)})
    flash("Student deleted successfully!", "success")
    return redirect(url_for("admin.manage_students"))


# -------------------- ASSIGN ROOM TO STUDENT --------------------
@admin.route("/students/assign_room/<id>", methods=["GET", "POST"])
def assign_room(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    db = mongo.cx["hosteler"]
    student = db["hostel_data"].find_one({"_id": ObjectId(id)})

    rooms = list(db["rooms"].find({"available_beds": {"$gt": 0}}))

    if request.method == "POST":
        room_no = request.form.get("room_no")
        room = db["rooms"].find_one({"room_no": room_no})

        if not room:
            flash("Room not found!", "danger")
            return redirect(url_for("admin.assign_room", id=id))

        old_room = student.get("room_no")
        if old_room:
            db["rooms"].update_one(
                {"room_no": old_room},
                {"$inc": {"occupied": -1, "available_beds": 1}}
            )

        db["hostel_data"].update_one(
            {"_id": ObjectId(id)},
            {"$set": {
                "room_no": room["room_no"],
                "room_block": room.get("block"),
                "room_floor": room.get("floor")
            }}
        )

        db["rooms"].update_one(
            {"room_no": room_no},
            {"$inc": {"occupied": 1, "available_beds": -1}}
        )

        flash("Room assigned successfully!", "success")
        return redirect(url_for("admin.manage_students"))

    return render_template("admin/assign_room.html", student=student, rooms=rooms)


# -------------------- DIRECT ASSIGN ROOM --------------------
@admin.route("/rooms/assign/<room_no>", methods=["GET", "POST"])
def assign_room_direct(room_no):
    if not admin_required():
        return redirect(url_for("admin.login"))

    db = mongo.cx["hosteler"]
    room = db["rooms"].find_one({"room_no": room_no})
    students = list(db["hostel_data"].find())

    if request.method == "POST":
        student_id = request.form.get("student_id")
        student = db["hostel_data"].find_one({"_id": ObjectId(student_id)})

        old_room = student.get("room_no")
        if old_room:
            db["rooms"].update_one(
                {"room_no": old_room},
                {"$inc": {"occupied": -1, "available_beds": 1}}
            )

        db["hostel_data"].update_one(
            {"_id": ObjectId(student_id)},
            {"$set": {
                "room_no": room_no,
                "room_block": room.get("block"),
                "room_floor": room.get("floor")
            }}
        )

        db["rooms"].update_one(
            {"room_no": room_no},
            {"$inc": {"occupied": 1, "available_beds": -1}}
        )

        flash("Room assigned successfully!", "success")
        return redirect(url_for("admin.manage_rooms"))

    return render_template("admin/assign_room_direct.html", room=room, students=students)


# -------------------- ROOM MANAGEMENT --------------------
@admin.route("/rooms")
def manage_rooms():
    if not admin_required():
        return redirect(url_for("admin.login"))

    rooms = list(mongo.cx["hosteler"]["rooms"].find())
    return render_template("admin/manage_rooms.html", rooms=rooms)


@admin.route("/add_room", methods=["GET", "POST"])
def add_room():
    if not admin_required():
        return redirect(url_for("admin.login"))

    if request.method == "POST":
        db = mongo.cx["hosteler"]

        capacity = int(request.form["capacity"])
        occupied = int(request.form["occupied"])

        if occupied > capacity:
            flash("Occupied cannot exceed capacity!", "danger")
            return redirect(url_for("admin.add_room"))

        db["rooms"].insert_one({
            "room_no": request.form["room_no"],
            "capacity": capacity,
            "occupied": occupied,
            "available_beds": capacity - occupied,
            "floor": request.form["floor"],
            "block": request.form["block"]
        })

        flash("Room added successfully!", "success")
        return redirect(url_for("admin.manage_rooms"))

    return render_template("admin/add_room.html")


@admin.route("/edit_room/<id>", methods=["GET", "POST"])
def edit_room(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    db = mongo.cx["hosteler"]
    room = db["rooms"].find_one({"_id": ObjectId(id)})

    if request.method == "POST":
        capacity = int(request.form["capacity"])
        occupied = int(request.form["occupied"])

        if occupied > capacity:
            flash("Occupied cannot exceed capacity!", "danger")
            return redirect(url_for("admin.edit_room", id=id))

        db["rooms"].update_one(
            {"_id": ObjectId(id)},
            {"$set": {
                "room_no": request.form["room_no"],
                "capacity": capacity,
                "occupied": occupied,
                "available_beds": capacity - occupied,
                "floor": request.form["floor"],
                "block": request.form["block"]
            }}
        )

        flash("Room updated!", "success")
        return redirect(url_for("admin.manage_rooms"))

    return render_template("admin/edit_room.html", room=room)


@admin.route("/delete_room/<id>")
def delete_room(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    db = mongo.cx["hosteler"]
    room = db["rooms"].find_one({"_id": ObjectId(id)})

    if room:
        db["hostel_data"].update_many(
            {"room_no": room["room_no"]},
            {"$set": {"room_no": "", "room_block": "", "room_floor": ""}}
        )

        db["rooms"].delete_one({"_id": ObjectId(id)})

    flash("Room deleted!", "success")
    return redirect(url_for("admin.manage_rooms"))


# -------------------- FEE MANAGEMENT --------------------
@admin.route("/fees")
def fees():
    if not admin_required():
        return redirect(url_for("admin.login"))

    fees = list(mongo.cx["hosteler"]["fees"].find())
    return render_template("admin/fee_management.html", fees=fees)


@admin.route("/add_fee", methods=["GET", "POST"])
def add_fee():
    if not admin_required():
        return redirect(url_for("admin.login"))

    db = mongo.cx["hosteler"]
    students = list(db["hostel_data"].find())

    if request.method == "POST":
        prn = request.form["student_prn"]
        stu = db["hostel_data"].find_one({"prn": prn})

        total = int(request.form["total"])
        paid = int(request.form["paid"])
        pending = total - paid

        db["fees"].insert_one({
            "student_prn": prn,
            "student_name": stu.get("full_name", "Unknown"),
            "semester": request.form["semester"],
            "total": total,
            "paid": paid,
            "pending": pending,
            "status": "Paid" if pending == 0 else "Pending"
        })

        flash("Fee added!", "success")
        return redirect(url_for("admin.fees"))

    return render_template("admin/add_fee.html", students=students)


@admin.route("/fees/delete/<id>")
def delete_fee(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    mongo.cx["hosteler"]["fees"].delete_one({"_id": ObjectId(id)})
    flash("Fee deleted!", "success")
    return redirect(url_for("admin.fees"))


# -------------------- COMPLAINTS --------------------
@admin.route("/complaints")
def complaints():
    if not admin_required():
        return redirect(url_for("admin.login"))

    comps = list(mongo.cx["hosteler"]["complaints"].find())
    return render_template("admin/complaints.html", complaints=comps)


@admin.route("/complaints/reply/<id>", methods=["POST"])
def complaint_reply(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    reply = request.form.get("admin_reply")
    status = request.form.get("status")

    mongo.cx["hosteler"]["complaints"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "admin_reply": reply,
            "status": status
        }}
    )

    flash("Reply sent!", "success")
    return redirect(url_for("admin.complaints"))


@admin.route("/complaints/delete/<id>")
def delete_complaint(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    mongo.cx["hosteler"]["complaints"].delete_one({"_id": ObjectId(id)})
    flash("Complaint deleted!", "success")
    return redirect(url_for("admin.complaints"))


# -------------------- LEAVE REQUESTS --------------------
@admin.route("/leave_requests")
def leave_requests():
    if not admin_required():
        return redirect(url_for("admin.login"))

    db = mongo.cx["hosteler"]
    leaves = list(db["leave_requests"].find())

    for l in leaves:
        stu = db["hostel_data"].find_one({"prn": l.get("student_prn")})

        # SAFE NAME — 0% error
        if stu:
            l["student_name"] = (
                stu.get("full_name") or
                stu.get("name") or
                stu.get("student_name") or
                stu.get("fullname") or
                "Unknown"
            )
        else:
            l["student_name"] = "Unknown"

    return render_template("admin/leave_requests.html", leaves=leaves)

# -------------------- UPDATE LEAVE STATUS (AJAX) --------------------
@admin.route("/update_leave/<id>/<status>", methods=["POST"])
def update_leave(id, status):
    if not admin_required():
        return {"success": False, "msg": "Unauthorized"}

    valid_status = ["Pending", "Approved", "Rejected"]
    if status not in valid_status:
        status = "Pending"

    mongo.cx["hosteler"]["leave_requests"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": status}}
    )

    return {"success": True, "status": status}



# -------------------- DELETE LEAVE --------------------
@admin.route("/leave/delete/<id>")
def delete_leave(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    mongo.cx["hosteler"]["leave_requests"].delete_one({"_id": ObjectId(id)})

    flash("Leave deleted!", "success")
    return redirect(url_for("admin.leave_requests"))


# -------------------- ADMIN: REPLY TO LEAVE REQUEST --------------------
@admin.route("/leave/reply/<id>", methods=["POST"])
def leave_reply(id):
    if not admin_required():
        return redirect(url_for("admin.login"))

    reply_text = request.form.get("reply", "").strip()
    status = request.form.get("status", "").strip()

    # validate status
    if status not in ["Pending", "Approved", "Rejected"]:
        status = "Pending"

    db = mongo.cx["hosteler"]
    # verify leave exists
    leave_doc = db["leave_requests"].find_one({"_id": ObjectId(id)})
    if not leave_doc:
        flash("Leave request not found.", "danger")
        return redirect(url_for("admin.leave_requests"))

    db["leave_requests"].update_one(
        {"_id": ObjectId(id)},
        {"$set": {"admin_reply": reply_text, "status": status}}
    )

    flash("Leave reply updated successfully!", "success")
    return redirect(url_for("admin.leave_requests"))



# -------------------- DOWNLOAD STUDENTS EXCEL --------------------
@admin.route("/download/students/excel")
def download_students_excel():
    db = mongo.cx["hosteler"]
    students = list(db["hostel_data"].find())

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Students Report"
    ws.append(["Full Name", "PRN", "Department", "Year", "Mobile", "Room No"])

    for s in students:

        name = s.get("fullname", "")   # <-- YOUR CORRECT FIELD

        ws.append([
            name,
            s.get("prn", ""),
            s.get("department", ""),
            s.get("year", ""),
            s.get("mobile", ""),
            s.get("room_no", "")
        ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return send_file(
        stream,
        as_attachment=True,
        download_name="students_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )



# -------------------- DOWNLOAD STUDENTS PDF (WITH PHOTO) --------------------
@admin.route("/download/students/pdf")
def download_students_pdf():
    db = mongo.cx["hosteler"]
    students = list(db["hostel_data"].find())

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Students Report")

    y = 760
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, "Students Report")
    y -= 40

    pdf.setFont("Helvetica", 10)

    for s in students:

        name = s.get("fullname", "")   # <-- YOUR FIELD FOR NAME

        # PHOTO (Your field name = "photo")
        img_name = s.get("photo")
        img_path = None

        if img_name:
            img_path = os.path.join("static", "uploads", img_name)

        # Draw image
        if img_path and os.path.exists(img_path):
            try:
                pdf.drawImage(img_path, 50, y - 10, width=50, height=50)
            except:
                pass

        # Student text
        pdf.drawString(120, y + 25, f"Name: {name}")
        pdf.drawString(120, y + 10, f"PRN: {s.get('prn', '')}")
        pdf.drawString(120, y - 5, f"Dept: {s.get('department', '')}")
        pdf.drawString(120, y - 20, f"Year: {s.get('year', '')}   Room: {s.get('room_no', '')}")

        y -= 85

        if y < 100:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 760

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="students_report.pdf",
        mimetype="application/pdf"
    )



# -------------------- DOWNLOAD ROOMS EXCEL/PDF --------------------
@admin.route("/download/rooms/excel")
def download_rooms_excel():
    rooms = list(mongo.cx["hosteler"]["rooms"].find())

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rooms Report"
    ws.append(["Room No", "Capacity", "Occupied", "Available Beds", "Block", "Floor"])

    for r in rooms:
        ws.append([
            r.get("room_no", ""),
            r.get("capacity", ""),
            r.get("occupied", ""),
            r.get("available_beds", ""),
            r.get("block", ""),
            r.get("floor", "")
        ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return send_file(
        stream,
        as_attachment=True,
        download_name="rooms_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@admin.route("/download/rooms/pdf")
def download_rooms_pdf():
    rooms = list(mongo.cx["hosteler"]["rooms"].find())

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Rooms Report")

    y = 750
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "Rooms Report")
    y -= 30

    pdf.setFont("Helvetica", 10)
    for r in rooms:
        line = f"Room {r.get('room_no')} | Block {r.get('block')} | Floor {r.get('floor')} | Beds {r.get('occupied')}/{r.get('capacity')}"
        pdf.drawString(50, y, line)
        y -= 18

        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="rooms_report.pdf",
        mimetype="application/pdf"
    )


# -------------------- DOWNLOAD FEES EXCEL/PDF --------------------
@admin.route("/download/fees/excel")
def download_fees_excel():
    data = list(mongo.cx["hosteler"]["fees"].find())

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fees Report"
    ws.append(["Name", "PRN", "Semester", "Total", "Paid", "Pending", "Status"])

    for f in data:
        ws.append([
            f.get("student_name"),
            f.get("student_prn"),
            f.get("semester"),
            f.get("total"),
            f.get("paid"),
            f.get("pending"),
            f.get("status")
        ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return send_file(
        stream,
        as_attachment=True,
        download_name="fees_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@admin.route("/download/fees/pdf")
def download_fees_pdf():
    data = list(mongo.cx["hosteler"]["fees"].find())

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Fees Report")

    y = 750
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "Fees Report")
    y -= 30

    pdf.setFont("Helvetica", 10)
    for f in data:
        line = f"{f.get('student_name')} | PRN {f.get('student_prn')} | Paid {f.get('paid')}/{f.get('total')} | Pending {f.get('pending')}"
        pdf.drawString(50, y, line)
        y -= 18

        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="fees_report.pdf",
        mimetype="application/pdf"
    )


# -------------------- DOWNLOAD COMPLAINTS EXCEL/PDF --------------------
@admin.route("/download/complaints/excel")
def download_complaints_excel():
    data = list(mongo.cx["hosteler"]["complaints"].find())

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Complaints Report"
    ws.append(["Name", "PRN", "Subject", "Message", "Admin Reply", "Status"])

    for c in data:
        ws.append([
            c.get("student_name"),
            c.get("student_prn"),
            c.get("subject"),
            c.get("message"),
            c.get("admin_reply", ""),
            c.get("status")
        ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return send_file(
        stream,
        as_attachment=True,
        download_name="complaints_report.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@admin.route("/download/complaints/pdf")
def download_complaints_pdf():
    data = list(mongo.cx["hosteler"]["complaints"].find())

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Complaints Report")

    y = 750
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "Complaints Report")
    y -= 30

    pdf.setFont("Helvetica", 10)
    for c in data:
        line = f"{c.get('student_name')} | {c.get('subject')} | {c.get('status')}"
        pdf.drawString(50, y, line)
        y -= 18

        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="complaints_report.pdf",
        mimetype="application/pdf"
    )


# -------------------- DOWNLOAD LEAVES EXCEL/PDF --------------------
@admin.route("/download/leaves/excel")
def download_leaves_excel():
    data = list(mongo.cx["hosteler"]["leave_requests"].find())

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leave Requests"
    ws.append(["Name", "PRN", "From", "To", "Days", "Reason", "Status"])

    for l in data:
        ws.append([
            l.get("student_name"),
            l.get("student_prn"),
            l.get("from_date"),
            l.get("to_date"),
            l.get("days"),
            l.get("reason"),
            l.get("status")
        ])

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return send_file(
        stream,
        as_attachment=True,
        download_name="leave_requests.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@admin.route("/download/leaves/pdf")
def download_leaves_pdf():
    data = list(mongo.cx["hosteler"]["leave_requests"].find())

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Leave Requests Report")

    y = 750
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "Leave Requests Report")
    y -= 30

    pdf.setFont("Helvetica", 10)
    for l in data:
        line = f"{l.get('student_name')} | {l.get('from_date')} - {l.get('to_date')} | {l.get('status')}"
        pdf.drawString(50, y, line)
        y -= 18

        if y < 50:
            pdf.showPage()
            y = 750

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="leave_requests.pdf",
        mimetype="application/pdf"
    )


# -------------------- LOGOUT --------------------
@admin.route("/logout")
def logout():
    session.clear()
    flash("Logged out!", "success")
    return redirect(url_for("main.login"))
