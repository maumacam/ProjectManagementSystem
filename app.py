from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector

app = Flask(__name__)
app.secret_key = "your_secret_key"  # needed for sessions

# MySQL connection
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="project_management"
)
cursor = conn.cursor(dictionary=True)

# Home route
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

# Signup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        # Check if username exists
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        existing_user = cursor.fetchone()
        if existing_user:
            flash("Username already exists!")
            return redirect(url_for('signup'))

        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
        conn.commit()
        flash("Account created! Please login.")
        return redirect(url_for('login'))
    return render_template('signup.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password")
            return redirect(url_for('login'))
    return render_template('login.html')

# Dashboard (main project view)
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # ===== DASHBOARD STATS =====
    cursor.execute("SELECT COUNT(*) AS total_projects FROM projects WHERE user_id=%s", (user_id,))
    total_projects = cursor.fetchone()['total_projects']

    cursor.execute("""
        SELECT COUNT(*) AS total_tasks
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        WHERE p.user_id=%s
    """, (user_id,))
    total_tasks = cursor.fetchone()['total_tasks']

    cursor.execute("""
        SELECT COUNT(*) AS in_progress
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        WHERE p.user_id=%s AND t.status='In Progress'
    """, (user_id,))
    in_progress = cursor.fetchone()['in_progress']

    cursor.execute("""
        SELECT COUNT(*) AS completed
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        WHERE p.user_id=%s AND t.status='Done'
    """, (user_id,))
    completed = cursor.fetchone()['completed']

    # ===== PROJECTS =====
    cursor.execute("SELECT * FROM projects WHERE user_id=%s", (user_id,))
    projects = cursor.fetchall()

    for project in projects:
        cursor.execute("SELECT COUNT(*) AS total FROM tasks WHERE project_id=%s", (project['id'],))
        total = cursor.fetchone()['total']

        cursor.execute("""
            SELECT COUNT(*) AS done FROM tasks
            WHERE project_id=%s AND status='Done'
        """, (project['id'],))
        done = cursor.fetchone()['done']

        project['progress'] = int((done / total) * 100) if total > 0 else 0

        cursor.execute("SELECT * FROM tasks WHERE project_id=%s", (project['id'],))
        project['tasks'] = cursor.fetchall()

    return render_template(
        'dashboard.html',
        username=session['username'],
        total_projects=total_projects,
        total_tasks=total_tasks,
        in_progress=in_progress,
        completed=completed,
        projects=projects
    )

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# Show all projects for logged-in user
@app.route('/projects')
def projects():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor.execute("SELECT * FROM projects WHERE user_id=%s", (session['user_id'],))
    projects = cursor.fetchall()
    return render_template('projects.html', projects=projects)

# Add new project
@app.route('/new_project', methods=['GET', 'POST'])
def new_project():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        deadline = request.form['deadline']

        cursor.execute(
            "INSERT INTO projects (name, description, deadline, user_id) VALUES (%s, %s, %s, %s)",
            (name, description, deadline, session['user_id'])
        )
        conn.commit()
        return redirect(url_for('dashboard'))
    return render_template('new_project.html')

# Show tasks for a project
@app.route('/projects/<int:project_id>/tasks')
def tasks(project_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor.execute("SELECT * FROM tasks WHERE project_id=%s", (project_id,))
    tasks = cursor.fetchall()
    return render_template('tasks.html', tasks=tasks, project_id=project_id)

# Add new task
@app.route('/projects/<int:project_id>/tasks/new', methods=['GET', 'POST'])
def new_task(project_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        assigned_to = request.form['assigned_to']
        status = request.form['status']
        deadline = request.form['deadline']

        cursor.execute(
            "INSERT INTO tasks (project_id, title, description, assigned_to, status, deadline) VALUES (%s, %s, %s, %s, %s, %s)",
            (project_id, title, description, assigned_to, status, deadline)
        )
        conn.commit()
        return redirect(url_for('tasks', project_id=project_id))
    return render_template('new_task.html', project_id=project_id)

# Edit Project
@app.route('/edit_project/<int:project_id>', methods=['GET', 'POST'])
def edit_project(project_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor.execute("SELECT * FROM projects WHERE id=%s AND user_id=%s", (project_id, session['user_id']))
    project = cursor.fetchone()
    if not project:
        return "Project not found or access denied"

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        deadline = request.form['deadline']

        cursor.execute(
            "UPDATE projects SET name=%s, description=%s, deadline=%s WHERE id=%s",
            (name, description, deadline, project_id)
        )
        conn.commit()
        return redirect(url_for('projects'))
    return render_template('edit_project.html', project=project)

# Delete Project
@app.route('/delete_project/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Delete tasks first to maintain foreign key constraint
    cursor.execute("DELETE FROM tasks WHERE project_id=%s", (project_id,))
    cursor.execute("DELETE FROM projects WHERE id=%s AND user_id=%s", (project_id, session['user_id']))
    conn.commit()
    return redirect(url_for('projects'))


if __name__ == "__main__":
    app.run(debug=True)
