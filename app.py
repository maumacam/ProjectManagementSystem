import os
from datetime import datetime
from bson.objectid import ObjectId
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'fallback-secret-key-change-this')

# =============================
# MONGODB CONNECTION with error handling
# =============================
app.config["MONGO_URI"] = os.getenv('MONGO_URI', "mongodb://localhost:27017/project_management")
mongo = PyMongo(app)
db = mongo.db

# Test MongoDB connection
try:
    # The ismaster command is cheap and does not require auth
    mongo.cx.admin.command('ismaster')
    print("MongoDB connection successful!")
except Exception as e:
    print(f"MongoDB connection error: {e}")

# =============================
# DECORATORS
# =============================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first!', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_user_projects(user_id):
    """Helper function to get user's projects with task counts"""
    projects = list(db.projects.find({"user_id": user_id}))
    
    for project in projects:
        project['id'] = str(project['_id'])
        project_id_str = str(project['_id'])
        
        # Get task counts for each status
        todo_count = db.tasks.count_documents({"project_id": project_id_str, "status": "To Do"})
        in_progress_count = db.tasks.count_documents({"project_id": project_id_str, "status": "In Progress"})
        done_count = db.tasks.count_documents({"project_id": project_id_str, "status": "Done"})
        total_count = todo_count + in_progress_count + done_count
        
        # Calculate progress
        project['progress'] = int((done_count / total_count) * 100) if total_count > 0 else 0
        project['total_tasks'] = total_count
        project['todo_count'] = todo_count
        project['in_progress_count'] = in_progress_count
        project['done_count'] = done_count
        
        # Format deadline
        if 'deadline' in project and project['deadline']:
            try:
                project['deadline_formatted'] = datetime.strptime(project['deadline'], '%Y-%m-%d').strftime('%b %d, %Y')
            except:
                project['deadline_formatted'] = project['deadline']
    
    return projects

# =============================
# ROUTES
# =============================

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        email = request.form.get('email', '').strip()
        
        # Validation
        if not username or not password:
            flash('Username and password are required!', 'error')
            return redirect(url_for('signup'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long!', 'error')
            return redirect(url_for('signup'))
        
        # Check if user exists
        if db.users.find_one({"username": username}):
            flash('Username already exists!', 'error')
            return redirect(url_for('signup'))
        
        if email and db.users.find_one({"email": email}):
            flash('Email already registered!', 'error')
            return redirect(url_for('signup'))
        
        # Create user
        hashed_password = generate_password_hash(password)
        user_data = {
            "username": username,
            "password": hashed_password,
            "email": email,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        db.users.insert_one(user_data)
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        user = db.users.find_one({"username": username})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['login_time'] = datetime.now().isoformat()
            
            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    
    # Get user's projects with stats
    projects = get_user_projects(user_id)
    
    # Calculate overall stats
    total_projects = len(projects)
    total_tasks = sum(p['total_tasks'] for p in projects)
    in_progress_tasks = sum(p['in_progress_count'] for p in projects)
    completed_tasks = sum(p['done_count'] for p in projects)
    
    # Get recent tasks
    user_projects_ids = [p['id'] for p in projects]
    recent_tasks = []
    if user_projects_ids:
        recent_tasks = list(db.tasks.find(
            {"project_id": {"$in": user_projects_ids}}
        ).sort("_id", -1).limit(5))
        
        for task in recent_tasks:
            task['id'] = str(task['_id'])
            # Get project name for each task
            project = db.projects.find_one({"_id": ObjectId(task['project_id'])})
            task['project_name'] = project['name'] if project else 'Unknown Project'
    
    return render_template(
        'dashboard.html',
        username=session['username'],
        total_projects=total_projects,
        total_tasks=total_tasks,
        in_progress=in_progress_tasks,
        completed=completed_tasks,
        projects=projects,
        recent_tasks=recent_tasks
    )

@app.route('/projects')
@login_required
def projects():
    projects = get_user_projects(session['user_id'])
    return render_template('projects.html', projects=projects)

@app.route('/new_project', methods=['GET', 'POST'])
@login_required
def new_project():
    if request.method == 'POST':
        name = request.form['name'].strip()
        description = request.form.get('description', '').strip()
        deadline = request.form.get('deadline', '')
        
        if not name:
            flash('Project name is required!', 'error')
            return redirect(url_for('new_project'))
        
        project_data = {
            "name": name,
            "description": description,
            "deadline": deadline if deadline else None,
            "user_id": session['user_id'],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        result = db.projects.insert_one(project_data)
        flash('Project created successfully!', 'success')
        return redirect(url_for('projects'))
    
    return render_template('new_project.html')

@app.route('/project/<project_id>')
@login_required
def view_project(project_id):
    project = db.projects.find_one({"_id": ObjectId(project_id), "user_id": session['user_id']})
    if not project:
        flash('Project not found!', 'error')
        return redirect(url_for('projects'))
    
    # Get all tasks for this project
    tasks = list(db.tasks.find({"project_id": project_id}).sort("created_at", -1))
    
    # Group tasks by status for kanban view
    todo = [t for t in tasks if t['status'] == 'To Do']
    in_progress = [t for t in tasks if t['status'] == 'In Progress']
    done = [t for t in tasks if t['status'] == 'Done']
    
    # Format tasks for display
    for task_list in [todo, in_progress, done]:
        for task in task_list:
            task['id'] = str(task['_id'])
            if 'deadline' in task and task['deadline']:
                try:
                    task['deadline_formatted'] = datetime.strptime(task['deadline'], '%Y-%m-%d').strftime('%b %d, %Y')
                except:
                    task['deadline_formatted'] = task['deadline']
    
    return render_template('project_detail.html', 
                         project=project, 
                         todo=todo, 
                         in_progress=in_progress, 
                         done=done)

@app.route('/project/<project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    project = db.projects.find_one({"_id": ObjectId(project_id), "user_id": session['user_id']})
    if not project:
        flash('Project not found!', 'error')
        return redirect(url_for('projects'))
    
    if request.method == 'POST':
        name = request.form['name'].strip()
        description = request.form.get('description', '').strip()
        deadline = request.form.get('deadline', '')
        
        if not name:
            flash('Project name is required!', 'error')
            return redirect(url_for('edit_project', project_id=project_id))
        
        update_data = {
            "name": name,
            "description": description,
            "deadline": deadline if deadline else None,
            "updated_at": datetime.now()
        }
        
        db.projects.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": update_data}
        )
        
        flash('Project updated successfully!', 'success')
        return redirect(url_for('view_project', project_id=project_id))
    
    return render_template('edit_project.html', project=project)

@app.route('/project/<project_id>/delete', methods=['POST'])
@login_required
def delete_project(project_id):
    # Delete all tasks first
    db.tasks.delete_many({"project_id": project_id})
    # Delete the project
    result = db.projects.delete_one({"_id": ObjectId(project_id), "user_id": session['user_id']})
    
    if result.deleted_count > 0:
        flash('Project deleted successfully!', 'success')
    else:
        flash('Project not found!', 'error')
    
    return redirect(url_for('projects'))

@app.route('/project/<project_id>/tasks/new', methods=['GET', 'POST'])
@login_required
def new_task(project_id):
    project = db.projects.find_one({"_id": ObjectId(project_id), "user_id": session['user_id']})
    if not project:
        flash('Project not found!', 'error')
        return redirect(url_for('projects'))
    
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description', '').strip()
        assigned_to = request.form.get('assigned_to', '').strip()
        status = request.form['status']
        deadline = request.form.get('deadline', '')
        priority = request.form.get('priority', 'Medium')
        
        if not title:
            flash('Task title is required!', 'error')
            return redirect(url_for('new_task', project_id=project_id))
        
        task_data = {
            "project_id": project_id,
            "title": title,
            "description": description,
            "assigned_to": assigned_to if assigned_to else None,
            "status": status,
            "deadline": deadline if deadline else None,
            "priority": priority,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        
        db.tasks.insert_one(task_data)
        flash('Task created successfully!', 'success')
        return redirect(url_for('view_project', project_id=project_id))
    
    return render_template('new_task.html', project=project)

@app.route('/task/<task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    task = db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        flash('Task not found!', 'error')
        return redirect(url_for('dashboard'))
    
    # Check if user owns the project
    project = db.projects.find_one({"_id": ObjectId(task['project_id']), "user_id": session['user_id']})
    if not project:
        flash('Access denied!', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form.get('description', '').strip()
        assigned_to = request.form.get('assigned_to', '').strip()
        status = request.form['status']
        deadline = request.form.get('deadline', '')
        priority = request.form.get('priority', 'Medium')
        
        if not title:
            flash('Task title is required!', 'error')
            return redirect(url_for('edit_task', task_id=task_id))
        
        update_data = {
            "title": title,
            "description": description,
            "assigned_to": assigned_to if assigned_to else None,
            "status": status,
            "deadline": deadline if deadline else None,
            "priority": priority,
            "updated_at": datetime.now()
        }
        
        db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": update_data}
        )
        
        flash('Task updated successfully!', 'success')
        return redirect(url_for('view_project', project_id=task['project_id']))
    
    return render_template('edit_task.html', task=task, project=project)

@app.route('/task/<task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    task = db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        flash('Task not found!', 'error')
        return redirect(url_for('dashboard'))
    
    # Check if user owns the project
    project = db.projects.find_one({"_id": ObjectId(task['project_id']), "user_id": session['user_id']})
    if not project:
        flash('Access denied!', 'error')
        return redirect(url_for('dashboard'))
    
    db.tasks.delete_one({"_id": ObjectId(task_id)})
    flash('Task deleted successfully!', 'success')
    
    return redirect(url_for('view_project', project_id=task['project_id']))

@app.route('/api/update_task_status', methods=['POST'])
@login_required
def update_task_status():
    data = request.get_json()
    task_id = data.get('task_id')
    status = data.get('status')
    
    if not task_id or not status:
        return jsonify({'success': False, 'error': 'Missing data'}), 400
    
    task = db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        return jsonify({'success': False, 'error': 'Task not found'}), 404
    
    # Check if user owns the project
    project = db.projects.find_one({"_id": ObjectId(task['project_id']), "user_id": session['user_id']})
    if not project:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    # Update task status
    db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"status": status, "updated_at": datetime.now()}}
    )
    
    # Calculate new progress for the project
    project_id = task['project_id']
    total = db.tasks.count_documents({"project_id": project_id})
    done = db.tasks.count_documents({"project_id": project_id, "status": "Done"})
    progress = int((done / total) * 100) if total > 0 else 0
    
    return jsonify({
        'success': True, 
        'progress': progress, 
        'project_id': project_id,
        'task_id': task_id,
        'new_status': status
    })

@app.route('/profile')
@login_required
def profile():
    user = db.users.find_one({"_id": ObjectId(session['user_id'])})
    return render_template('profile.html', user=user)

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)