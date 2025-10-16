from flask import Flask, redirect,jsonify,request,render_template,url_for,session
import os
from werkzeug.utils import secure_filename
import sqlite3
import qrcode
import requests
import psycopg2
from difflib import get_close_matches


app=Flask(__name__)
# secret key
app.secret_key="your_secret_key_here"

UPLOAD_FOLDER=os.path.join('static','uploads')
ALLOWED_EXTENSIONS={'pdf','docx','txt','png','jpg'}
app.config['UPLOAD_FOLDER']=UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
  os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
  return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS #Checks if the file has an extension (like .pdf, .jpg). Splits the filename from the right (rsplit) → "notes.pdf" → "pdf". Converts it to lowercase (lower()) and checks if it’s in the allowed list.

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
  return psycopg2.connect(DATABASE_URL, sslmode='require')

# database
def init_db():
  conn=get_conn()
  c=conn.cursor()
  c.execute("""
  CREATE TABLE IF NOT EXISTS Users(
    id SERIAL PRIMARY KEY ,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL
  )
  """)

  c.execute("""
  CREATE TABLE IF NOT EXISTS Subjects(
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
  )
  """)

  c.execute("""
  CREATE TABLE IF NOT EXISTS Units(
    id SERIAL PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES Subjects(id),
    units TEXT NOT NULL
  )
  """)
  c.execute("""
  CREATE TABLE IF NOT EXISTS Notes(
    id SERIAL PRIMARY KEY,
    notes TEXT ,
    unit_id INTEGER NOT NULL REFERENCES Units(id)
  )
  """)

  c.execute("""
  CREATE TABLE IF NOT EXISTS MyNotes(
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES Users(id),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    qr_code TEXT,  
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )""")

  c.execute("""
  CREATE TABLE IF NOT EXISTS NoteShares(
    id SERIAL PRIMARY KEY,
    note_id INTEGER NOT NULL REFERENCES MyNotes(id),
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
  )
  """)
  conn.commit()
  conn.close()
init_db()


#home route
@app.route('/')
def home():
  return render_template('signin.html')
#signin route
@app.route('/signi/', methods=['GET','POST'])
def signi():
  if request.method=='POST':
    username=request.form['username'] 
    password=request.form['password']
    role=request.form['role']
    conn=get_conn()
    c=conn.cursor()
    c.execute("SELECT id FROM Users WHERE username=? AND password=? AND role=?",(username,password,role))
    user=c.fetchone()
    conn.close()
    if user:
      session["user_id"]=user[0]
      if role=="teacher":
        return redirect(url_for("dashboardteach"))
      else:
        return redirect(url_for("dashboardstud"))
    else:
      return "Invalid credentials"
  return render_template('signin.html')
#signup route
@app.route('/signp/',methods=["POST","GET"])
def signp():
  if request.method=="POST":
    username=request.form["username"]
    password=request.form["password"]
    role=request.form["role"]
    conn=get_conn()
    c=conn.cursor()
    try:
      c.execute("INSERT INTO Users (username,password,role) VALUES(%s,%s,%s)",(username,password,role))
      conn.commit()
    except sqlite3.IntegrityError:
      return "Username already exists"
    finally:
      conn.close()
    return redirect(url_for('signi'))

  return render_template('signup.html')
#dashboardteacher route
@app.route('/dashboardteach/')
def dashboardteach():
  if "user_id" not in session:
    return redirect(url_for("signi"))
  conn=get_conn()
  c=conn.cursor()
  c.execute("SELECT id,name FROM Subjects")
  subjects=c.fetchall()
  conn.close()
  return render_template("dashboardteacher.html",subjects=subjects)
#addsubject route
@app.route('/addsubject/',methods=['POST'])
def addsubject():
  if "user_id" not in session:
    return redirect(url_for("signi"))
  subject_name=request.form['subject_name']
  conn=get_conn()
  c=conn.cursor()
  try:
    c.execute("INSERT INTO Subjects (name) VALUES(%s)",(subject_name,))
    conn.commit()
  except sqlite3.IntegrityError:
    return "Subject already exists"
  finally:
    conn.close()
  return redirect(url_for('dashboardteach'))
#deletesubject route
@app.route('/deletesubject/<int:subject_id>',methods=['POST'])
def deletesubject(subject_id):
  if "user_id" not in session:
    return redirect(url_for("signi"))
  conn=get_conn()
  c=conn.cursor()
  try:
    c.execute("DELETE FROM Subjects WHERE id=%s",(subject_id,))
    conn.commit()
  except sqlite3.IntegrityError:
    return "Subject already exists"
  finally:
    conn.close()
  return redirect(url_for('dashboardteach'))
#units route
@app.route('/units/<int:subject_id>')
def units(subject_id):
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  c.execute("SELECT name FROM Subjects WHERE id=%s",(subject_id,))
  subject=c.fetchone()
  c.execute("SELECT id,units FROM Units WHERE subject_id=%s",(subject_id,))
  Units=c.fetchall()
  conn.close()
  return render_template("units.html",Units=Units,subject_id=subject_id)

#addunits route
@app.route('/addunits/<int:subject_id>',methods=['POST'])
def addunits(subject_id):
  unitname=request.form['unitname']
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  try:
    c.execute("INSERT INTO Units (subject_id,units) VaLUES (%s,%s)", (subject_id,unitname))
    conn.commit()
  except sqlite3.IntegrityError:
    return "Unit already exists"
  finally:
    conn.close()
  return redirect(url_for('units',subject_id=subject_id))

#deleteunits route
@app.route('/deleteunits/<int:unit_id>/<int:subject_id>',methods=['POST'])
def deleteunits(unit_id,subject_id):
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  try:
    c.execute("DELETE FROM Units WHERE id=%s",(unit_id,))
    conn.commit()
  except sqlite3.IntegrityError:
    return "Unit already deleted"
  finally:
    conn.close()
  return redirect(url_for('units',subject_id=subject_id))


#uploadnotes route
@app.route('/upload_note/<int:subject_id>', methods=['POST', 'GET'])
def upload_note(subject_id):
    if "user_id" not in session:
        return redirect(url_for("signi"))
    if request.method == 'GET':
        return redirect(url_for('units', subject_id=subject_id))
    file = request.files.get('file')
    unit_id = request.form.get('unit_id')

    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        conn = sqlite3.connect("notesapp.db")
        c = conn.cursor()
        c.execute("INSERT INTO Notes (notes, unit_id) VALUES (%s, %s)", (filename, unit_id))
        conn.commit()
        conn.close()

    return redirect(url_for('units', subject_id=subject_id))
#deletenotes route
@app.route('/delete_note/<int:note_id>/<int:unit_id>', methods=['POST'])
def delete_note(note_id, unit_id):
    if "user_id" not in session:
        return redirect(url_for("signi"))

    conn = sqlite3.connect("notesapp.db")
    c = conn.cursor()

    # First, get the filename to remove the file from uploads
    c.execute("SELECT notes FROM Notes WHERE id=%s", (note_id,))
    row = c.fetchone()
    if row:
        filename = row[0]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    # Delete from database
    c.execute("DELETE FROM Notes WHERE id=%s", (note_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('notes', unit_id=unit_id))



#showing notes
@app.route('/notes/<int:unit_id>')
def notes(unit_id):
  if "user_id" not in session:
    return redirect(url_for("signi"))
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  c.execute("SELECT units,subject_id FROM Units WHERE id=%s",(unit_id,))
  row=c.fetchone()
  if not row:
    conn.close()
    return "Note is not found"
  unit_name,subject_id=row
  c.execute("SELECT id,notes FROM Notes WHERE unit_id=%s",(unit_id,))
  notes_data=c.fetchall()

  conn.close()
  user_role=session.get("role","teacher")
  return render_template("notes.html",notes_data=notes_data,unit_name=unit_name,subject_id=subject_id,user_role=user_role,unit_id=unit_id)
#logout route
@app.route('/logout/')
def logout():
  session.pop("user_id",None)
  return redirect(url_for("signi"))

#dashboardstudentent route
@app.route('/dashboardstud/')
def dashboardstud():
  if "user_id" not in session:
    return redirect(url_for("signi"))
  student_id=session["user_id"]
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  c.execute("SELECT id,title,content,created_at,qr_code FROM  MyNotes WHERE student_id=%s",(student_id,))
  notes=c.fetchall()
  conn.close()
  return render_template("dashboardstudent.html",notes=notes,student_id=student_id)

#student route
@app.route('/student/')
def student():
  if "user_id" not in session:
    return redirect(url_for("signi"))
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  c.execute("SELECT id,name FROM Subjects")
  subjects=c.fetchall()
  conn.close()
  return render_template("student.html",subjects=subjects)
#unitsstud route
@app.route('/unitsstud/<int:subject_id>')
def unitsstud(subject_id):
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  c.execute("SELECT name FROM Subjects WHERE id=%s",(subject_id,))
  subject=c.fetchone()
  c.execute("SELECT id,units FROM Units WHERE subject_id=%s",(subject_id,))
  Units=c.fetchall()
  conn.close()
  return render_template("unitsstud.html",Units=Units,subject_id=subject_id)

#showingstud notes
@app.route('/notesstud/<int:unit_id>')
def notesstud(unit_id):
  if "user_id" not in session:
    return redirect(url_for("signi"))
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  c.execute("SELECT units,subject_id FROM Units WHERE id=%s",(unit_id,))
  row=c.fetchone()
  if not row:
    conn.close()
    return "Note is not found"
  unit_name,subject_id=row
  c.execute("SELECT id,notes FROM Notes WHERE unit_id=%s",(unit_id,))
  notes_data=c.fetchall()
  conn.close()
  user_role=session.get("role","student")
  return render_template("notesstud.html",notes_data=notes_data,unit_name=unit_name,subject_id=subject_id,user_role=user_role,unit_id=unit_id)


#----------------notes in the student dashboard-------------------------------

#addnotes route
@app.route('/add_note/<int:student_id>',methods=['POST','GET'])
def add_note(student_id):
  if request.method=='POST':
    title=request.form['title']
    content=request.form['content']
    conn=sqlite3.connect("notesapp.db")
    c=conn.cursor()
    c.execute("INSERT INTO MyNotes(student_id,title,content) VALUES(%s,%s,%s)",(student_id,title,content))
    conn.commit()

    note_id=c.lastrowid
    conn.close()

    qr_folder="static/qr_codes"
    os.makedirs(qr_folder,exist_ok=True)

    qr_data = f"{request.url_root}import_note/{note_id}"
    qr_img = qrcode.make(qr_data)
    qr_db_path = f"qr_codes/note_{note_id}.png" 
    qr_img.save(os.path.join("static", qr_db_path))

    conn = sqlite3.connect("notesapp.db")
    c = conn.cursor()
    c.execute("UPDATE MyNotes SET qr_code=%s WHERE id=%s", (qr_db_path, note_id))
    conn.commit()
    conn.close()
    return redirect(url_for("dashboardstud"))
  return render_template("add_note.html",student_id=student_id)

#viewnotes route
@app.route('/view_note/<int:note_id>')
def view_note(note_id):
    conn = sqlite3.connect("notesapp.db")
    c = conn.cursor()
    c.execute("SELECT title, content, created_at FROM MyNotes WHERE id=%s", (note_id,))
    note = c.fetchone()
    conn.close()

    if not note:
        return "Note not found"

    return render_template("view_note.html", note=note, note_id=note_id)


#deletenotes route
@app.route('/delete_note_student/<int:note_id>/<int:student_id>',methods=['POST'])
def delete_note_student(note_id,student_id):
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  c.execute("DELETE FROM MyNotes WHERE id=%s AND student_id=%s",(note_id,student_id))
  conn.commit()
  conn.close()
  return redirect(url_for("dashboardstud",student_id=student_id))

#editnotes route
@app.route('/update_note/<int:note_id>',methods=['POST'])
def update_note(note_id):
  title=request.form['title']
  content=request.form['content']
  student_id=request.form['student_id']
  conn=sqlite3.connect("notesapp.db")
  c=conn.cursor()
  c.execute("UPDATE MyNotes SET title=%s,content=%s WHERE id=%s",(title,content,note_id))
  conn.commit()
  conn.close()
  return redirect(url_for("dashboardstud",student_id=student_id))

#editnotes route
@app.route('/edit_note/<int:note_id>')
def edit_note(note_id):
    conn = sqlite3.connect("notesapp.db")
    c = conn.cursor()
    c.execute("SELECT id, title, content, student_id FROM MyNotes WHERE id=%s", (note_id,))
    note = c.fetchone()
    conn.close()
    if not note:
        return "Note not found"
    return render_template("edit_note.html", note=note)

#---------qr code route-------------------------------
@app.route('/scan_qr/')
def scan_qr():
    if "user_id" not in session:
        return redirect(url_for("signi"))
    return render_template("scan_qr.html")

@app.route('/import_note/<int:note_id>')
def import_note(note_id):
    if "user_id" not in session:
        return redirect(url_for("signi"))

    student_id = session["user_id"]

    conn = sqlite3.connect("notesapp.db")
    c = conn.cursor()

    # Get the note data
    c.execute("SELECT title, content FROM MyNotes WHERE id=%s", (note_id,))
    note = c.fetchone()

    if not note:
        conn.close()
        return "Note not found"

    title, content = note

    # Insert into the current student's notes
    c.execute("INSERT INTO MyNotes (student_id, title, content) VALUES (%s, %s, %s)",
              (student_id, title, content))
    conn.commit()
    conn.close()

    return redirect(url_for("dashboardstud"))

#-------------------------------huggingface api------------------------------------
HUGGINGFACE_API_KEY = "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"  # Set in Replit secrets

# Summarizer function
def summarize_text(text):
  API_URL = "https://api-inference.huggingface.co/models/sshleifer/distilbart-cnn-12-6"
  headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}

  # Prevent timeouts for long notes
  if len(text) > 1000:
      text = text[:1000]

  payload = {"inputs": text}

  try:
      response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
      response.raise_for_status()
      result = response.json()

      if isinstance(result, list) and "summary_text" in result[0]:
          return result[0]["summary_text"]
      return str(result[0])
  except Exception as e:
      return f"Error during summarization: {e}"








@app.route('/ai_chat/<int:note_id>', methods=['POST'])
def ai_chat(note_id):
    data = request.get_json()
    action = data.get("action")
    query = data.get("query", "")

    conn = sqlite3.connect("notesapp.db")
    c = conn.cursor()
    c.execute("SELECT content FROM MyNotes WHERE id=%s", (note_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"result": "Note not found."})

    note_content = row[0]

    try:
        if action == "summary":
            result_text = summarize_text(note_content)
        elif action == "question":
          sentences = [s.strip() for s in note_content.split('.') if s]
          keywords = query.lower().split()
          matched_sentences = []
          for sentence in sentences:
            score = sum(1 for word in keywords if word in sentence.lower())
            if score > 0:
                matched_sentences.append((score, sentence))

          if matched_sentences:
            matched_sentences.sort(reverse=True)
            best_sentence = matched_sentences[0][1]
            result_text = best_sentence
          else:
            result_text = "Sorry, I couldn't find an answer in the note."

        else:
            result_text = "Invalid action."

        return jsonify({"result": result_text})
    except Exception as e:
        return jsonify({"result": f"Error generating AI response: {e}"})



if __name__ == '__main__':
  import os
  port = int(os.environ.get('PORT', 5000))
  app.run(host='0.0.0.0', port=port)