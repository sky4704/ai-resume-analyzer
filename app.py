from flask import Flask, render_template, request, session, redirect, flash, url_for
from db import Base, engine, SessionLocal
from werkzeug.utils import secure_filename
import models
import gemini_ai
import PyPDF2
import docx
import json
from dotenv import load_dotenv
import bcrypt
import os
import re
import secrets

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("FLASK_SECRET_KEY")

app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

Base.metadata.create_all(bind=engine)

ALLOWED_EXTENSIONS = {"pdf", "docx"}

def allowed_file(filename):

    return "." in filename and \
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

#Home
@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")

    return redirect("/login")

def is_password_hashed(password_string):
    return bool(re.match(r'^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$', password_string))

#Signup
@app.route("/signup", methods=["GET", "POST"])
def signup():
    db = SessionLocal()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")
        try:
            existing_user = db.query(models.User).filter(models.User.email == email).first()
            if existing_user:
                flash("User already exists", "error")
                return redirect("/signup")
            
            hashed_password = bcrypt.hashpw(
                        password.encode("utf-8"),
                        bcrypt.gensalt()
                    ).decode("utf-8")

            user = models.User(email=email, password=hashed_password)
            db.add(user)
            db.commit()

            return redirect("/login")
        finally:
            db.close()

    return render_template("signup.html")

#Login
@app.route("/login", methods=["GET", "POST"])
def login():    
    db = SessionLocal()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")

        try:
            user = db.query(models.User).filter(models.User.email == email).first()
            if user:
                # Case 1: Password is already hashed
                if is_password_hashed(user.password):
                    valid_password = bcrypt.checkpw(
                                password.encode("utf-8"),  # Incoming plain text password as bytes
                                user.password.encode("utf-8")   # Stored string hash converted back to bytes
                            )
                    
                # Case 2: Password is in plain text, not hashed
                else:
                    valid_password = user.password == password

                    # If password is plain text, hash it right now and save to db
                    if valid_password:
                        hashed_password = bcrypt.hashpw(
                                    password.encode("utf-8"),
                                    bcrypt.gensalt()
                                ).decode("utf-8")

                        user.password = hashed_password
                        db.commit()

                    else:
                        valid_password = False

                if valid_password:
                    session["user"] = email
                    return redirect("/dashboard")
                
                flash("Invalid password!", "error")
            else:
                flash("Invalid user credentials!", "error")
            
        finally:
            db.close()

    return render_template("login.html")

#Dashboard
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")
    
    result = None

    if request.method == "POST":
        user_role = request.form.get("role")
        resume_text = request.form.get("resume", "").strip()

        file = request.files.get("file")

        if file and file.filename != "":
            filename = secure_filename(file.filename)
            if not allowed_file(filename):
                flash("Only PDF and DOCX files allowed", "error")
                result = {"error": "Only PDF and DOCX files allowed"}
                return render_template("dashboard.html", result=result)
            
            if file.filename.endswith(".pdf"):
                try:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text() or ""
                    resume_text = text
                except Exception as e:
                    result = {"error": f"Pdf error: {str(e)}"}
            elif file.filename.endswith(".docx"):
                try:
                    doc = docx.Document(file)
                    text = ""
                    for paragraph in doc.paragraphs:
                        text += paragraph.text + "\n"
                    resume_text = text
                except Exception as e:
                    result = {"error": f"Docx error: {str(e)}"}    

        if not resume_text and user_role:
            result = {"error": "Please upload or paste resume"}
            flash("Please upload or paste resume", "error")

            return render_template("dashboard.html",user=session["user"], result=result)
        try:
            result = gemini_ai.resume_analyzer(resume_text, user_role)

            if not isinstance(result, dict):

                result = {
                    "error": "Unexpected AI response"
                }

            #Save to db
            db = SessionLocal()
            try:
                user = db.query(models.User).filter_by(email=session["user"]).first()
                
                report = models.Report(
                    user_id=user.id,
                    resume_text=resume_text, 
                    result=json.dumps(result)
                    )

                db.add(report)
                db.commit()

            finally:
                db.close()

        except Exception as e:
            result = {"error": f"AI error: {str(e)}"}

    return render_template(
        "dashboard.html",
        user=session["user"],
        result=result
        )


@app.route("/history")
def history():
    if "user" not in session:
        return redirect("/login")

    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(email=session["user"]).first()
        reports = db.query(models.Report).filter_by(user_id=user.id).all()

        #Covert json string -> dict
        parsed_reports = []
        for report in reports:
            try:
                parsed_result = json.loads(report.result)

                # Backward compatibility

                parsed_result.setdefault("summary", "")

                parsed_result.setdefault("resume_score", 0)

                parsed_result.setdefault("skills", [])

                parsed_result.setdefault("missing_skills", [])

                parsed_result.setdefault("roadmap", [])

                parsed_result.setdefault("interview_questions", [])

            except:
                parsed_result = []

            parsed_reports.append({
                "resume": report.resume_text,
                "result": parsed_result
            })

        return render_template(
        "history.html",
        user=session["user"],
        reports=parsed_reports[::-1]
        )

    finally:
        db.close()


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")

@app.errorhandler(413)
def handle_large_files(error):
    flash("The file you uploaded exceeds the 2MB limit.Please try a smaller file with .pdf or .docx extension", "error")
    return redirect("/dashboard")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        db = SessionLocal()

        try:

            user = db.query(models.User).filter_by(
                email=email
            ).first()

            if not user:

                flash("Email not found", "error")

                return redirect("/forgot-password")

            # Generate secure token
            token = secrets.token_hex(32)

            user.reset_token = token

            db.commit()

            reset_link = url_for(
                "reset_password",
                token=token,
                _external=True
            )

            print("\nRESET LINK:")
            print(reset_link)
            print()

            flash(
                "Reset link generated. Check terminal.",
                "success"
            )

            return redirect("/login")

        finally:

            db.close()

    return render_template("forgot_password.html")

@app.route("/reset-password/<token>",methods=["GET", "POST"])
def reset_password(token):

    db = SessionLocal()

    try:

        user = db.query(models.User).filter_by(
            reset_token=token
        ).first()


        if not user:

            flash("Invalid or expired token", "error")

            return redirect("/login")

        user_email = user.email
        
        if request.method == "POST":

            password = request.form.get(
                "password",
                ""
            ).strip()

            hashed_password = bcrypt.hashpw(
                password.encode("utf-8"),
                bcrypt.gensalt()
            ).decode("utf-8")

            user.password = hashed_password

            # Remove token after use
            user.reset_token = None

            db.commit()

            flash(
                "Password reset successful",
                "success"
            )

            return redirect("/login")

        return render_template(
            "reset_password.html",
            user_email=user_email
        )

    finally:

        db.close()

@app.errorhandler(500)
def internal_server_error(error):

    return render_template(
        "500.html"
    ), 500

if __name__ == "__main__":
    app.run()
