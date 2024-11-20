from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Project
from config import Config
import os
import json
from io import BytesIO
from openai import OpenAI
from urllib.parse import urlparse
from dotenv import load_dotenv
import requests

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user)
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user is not None:
            flash('Username already exists')
            return redirect(url_for('register'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    users = User.query.all()
    projects = Project.query.all()
    return render_template('admin.html', users=users, projects=projects)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    if user == current_user:
        flash('You cannot delete your own account')
        return redirect(url_for('admin'))
    
    db.session.delete(user)
    db.session.commit()
    flash(f'User {user.username} has been deleted')
    return redirect(url_for('admin'))

@app.route('/admin/make_user_admin/<int:user_id>', methods=['POST'])
@login_required
def make_user_admin(user_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()
    flash(f'User {user.username} has been made an admin')
    return redirect(url_for('admin'))

@app.route('/admin/delete_project/<int:project_id>', methods=['POST'])
@login_required
def delete_project(project_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash(f'Project {project.name} has been deleted')
    return redirect(url_for('admin'))

@app.route('/admin/export_all_projects')
@login_required
def export_all_projects():
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    projects = Project.query.all()
    projects_data = [{'name': p.name, 'content': json.loads(p.content)} for p in projects]
    return send_file(BytesIO(json.dumps(projects_data, indent=2).encode()), mimetype='application/json', as_attachment=True, download_name='all_projects_export.json')

@app.route('/admin/import_projects', methods=['POST'])
@login_required
def import_projects():
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    
    if 'json_file' not in request.files:
        flash('No file part')
        return redirect(url_for('admin'))
    
    file = request.files['json_file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('admin'))
    
    if file and file.filename.endswith('.json'):
        try:
            content = json.loads(file.read().decode('utf-8'))
            imported_count = 0
            
            # Check if it's a single project or multiple projects
            if isinstance(content, dict) and 'nodes' in content and 'edges' in content:
                # Single project import
                project_name = file.filename.rsplit('.', 1)[0]
                imported_count = import_single_project(current_user.id, project_name, content)
            else:
                # Multiple projects import
                for project_name, project_data in content.items():
                    imported_count += import_single_project(current_user.id, project_name, project_data)
            
            flash(f'Successfully imported {imported_count} project(s)')
        except json.JSONDecodeError:
            flash('Invalid JSON file')
        except Exception as e:
            flash(f'Error importing projects: {str(e)}')
    else:
        flash('Invalid file type')
    
    return redirect(url_for('admin'))

def import_single_project(user_id, project_name, project_data):
    existing_project = Project.query.filter_by(user_id=user_id, name=project_name).first()
    if existing_project:
        existing_project.content = json.dumps(project_data)
        db.session.commit()
    else:
        new_project = Project(user_id=user_id, name=project_name, content=json.dumps(project_data))
        db.session.add(new_project)
        db.session.commit()
    return 1

@app.route('/save_project', methods=['POST'])
@login_required
def save_project():
    data = request.json
    project = Project.query.filter_by(name=data['name'], user_id=current_user.id).first()
    if project:
        project.content = json.dumps(data['content'])
    else:
        project = Project(name=data['name'], content=json.dumps(data['content']), user_id=current_user.id)
        db.session.add(project)
    db.session.commit()
    return jsonify(success=True)

@app.route('/get_projects')
@login_required
def get_projects():
    projects = Project.query.filter_by(user_id=current_user.id).all()
    return jsonify([{'id': p.id, 'name': p.name, 'content': json.loads(p.content)} for p in projects])

@app.route('/get_node_suggestions')
def get_node_suggestions():
    with open('node_suggestions.json', 'r') as f:
        suggestions = json.load(f)
    return jsonify(suggestions)

@app.route('/export_graph', methods=['POST'])
@login_required
def export_graph():
    graph_data = request.json
    json_data = json.dumps(graph_data, indent=2)
    return send_file(BytesIO(json_data.encode()), mimetype='application/json', as_attachment=True, download_name='graph_export.json')

@app.route('/import_graph', methods=['POST'])
@login_required
def import_graph():
    if 'file' not in request.files:
        return jsonify(success=False, error='No file part')
    file = request.files['file']
    if file.filename == '':
        return jsonify(success=False, error='No selected file')
    if file:
        try:
            graph_data = json.load(file)
            return jsonify(success=True, content=graph_data)
        except json.JSONDecodeError:
            return jsonify(success=False, error='Invalid JSON file')

@app.route('/admin/generate_graph', methods=['POST'])
@login_required
def generate_graph():
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Access denied'})

    prompt = request.json.get('prompt') if request.json else None
    if not prompt:
        return jsonify({'success': False, 'error': 'No prompt provided'})

    try:
        # Use OpenAI GPT to generate graph data
        graph_data = generate_graph_data_with_gpt(prompt)
        
        # Query OpenAlex API using the original prompt
        openalex_url = f'https://api.openalex.org/works?search={prompt}&per-page=5'
        print(f"\nQuerying OpenAlex with original prompt: {prompt}")
        
        papers = []
        response = requests.get(openalex_url)
        if response.status_code == 200:
            papers_data = response.json()
            papers = [
                {
                    'title': paper.get('title'),
                    'year': paper.get('publication_year'),
                    'doi': paper.get('doi'),
                    'authors': [author.get('author', {}).get('display_name') for author in paper.get('authorships', [])[:3]]
                }
                for paper in papers_data.get('results', [])
            ]
            
            # Still keep console output for debugging
            print("\nRelevant papers from OpenAlex:")
            for paper in papers:
                print(f"- {paper['title']} ({paper['year']})")
                print(f"  DOI: {paper['doi']}")
                print()
        
        return jsonify({
            'success': True, 
            'graph_data': graph_data,
            'papers': papers
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def generate_graph_data_with_gpt(prompt):
    client = OpenAI(
        api_key=os.environ.get('OPENAI_API_KEY'),
        organization=os.environ.get('OPENAI_ORGANIZATION_KEY')
    )
    
    # Prepare the prompt for GPT with the provided preamble   
    gpt_prompt = f"""
    You are an AI assistant and expert scientist, tasked with creating a comprehensive and detailed Directed Acyclic Graph (DAG) that illustrates causal mechanisms based on established scientific evidence. Your goal is to analyze the given prompt and generate a structured representation of the specific causal links described in the scientific literature, including relevant context, confounders, mediators, moderators, and indirect pathways. Sometimes, the scientific literature may not provide sufficient information to fully understand the causal relationships, and in those cases make sure you note so as to provide adequate context for the analysis (further instructions in the guidelines below). Sometimes the requests will be facetious, you can accommodate them and treat them as if they were serious, just make sure you note in the annotations that you are doing so.

    Please follow these guidelines:

    1. **Identify Key Concepts, Contextual Factors, and Confounders:**
       - Extract specific factors, processes, outcomes, and context factors mentioned or implied in the prompt.
       - Include potential **confounders**, **mediators**, **moderators**, and other variables that may influence the causal relationships.
       - Use your domain knowledge to include relevant intermediate steps and contextual factors supported by scientific evidence.
       - Include as many factors as you can find that are supported by evidence.

    2. **Determine Causal Relationships:**
       - Map out how each concept, context factor, or event causally influences others.
       - Include **direct and indirect pathways**, **interactions**, and complex relationships.
       - Capture biological, chemical, environmental, social, economic, and behavioral mechanisms as appropriate.
       - Always consider the existence of **intermediate steps** and **contextual factors** that may influence the causal relationships. For example, if age is a factor in the causal model, consider how it may influence the other factors and add edges as appropriate.

    3. **Create a Detailed and Comprehensive DAG Structure:**
       - Each node should represent a specific concept, factor, event, or variable.
       - Include nodes for confounders, mediators, moderators, and other relevant variables.
       - Each edge should represent a direct causal link from one node to another.
       - The DAG should reflect the **complexity of the causal relationships**, including multiple pathways and interconnected nodes, not just a simple linear sequence.

    4. **Ensure Graph Acyclicity:**
       - The graph must be acyclic with no circular dependencies.
       - Ensure that each node is connected to at least one other node.
       - Avoid redundant edges and self-loops.
       - If there is conflicting information that would lead to circular dependencies or cyclicity, prioritize the most important information and make a note in the annotations.

    5. **Provide Clear Labels and Annotations:**
       - **Nodes:**
         - Include 'id', 'label', and 'title' for each node.
         - 'label' should be concise yet descriptive.
         - 'title' should provide a brief explanation and possibly a reference to real scientific evidence (e.g., "Socioeconomic status influences smoking rates [Smith et al., 2020]"). Make sure these are actual references to scientific literature, otherwise describe what you have found.

    6. **Cite Sources:**
       - When possible, reference scientific studies or reviews that support each causal link (use placeholder citations if necessary) in the 'title' field.

    7. **Expand DAG**
        - Once the DAG is complete, go through all the nodes and ask yourself the same questions about causation between them. For example, if a node represents age, you might want to include edges from age to health, age to income, and age to education if relevant.
        - Expand the DAG by adding more nodes and edges to capture the full range of causal relationships.
        - Always make sure this is done based on evidence and not based on assumptions.
        

    8. **Output Format:**
       - Return the result as a JSON object with two keys: **'nodes'** and **'edges'**.
       - **'nodes'**: A list of objects, each with 'id', 'label', and 'title'.
       - **'edges'**: A list of objects, each with 'from' and 'to' keys representing connections between nodes.

    **Example Format:**

    
    {{
      "nodes": [
        {{"id": 1, "label": "Policy X Implementation", "title": "Introduction of Policy X to address issue Y"}},
        {{"id": 2, "label": "Resource Allocation", "title": "Policy X reallocates resources - no available peer-review reference, blog post at https://address.com"}},
        {{"id": 3, "label": "Service Access", "title": "Changes in access to services [Smith et al., 2020]"}},
        {{"id": 4, "label": "Outcome Y", "title": "Impact on Outcome Y"}},
        {{"id": 5, "label": "Socioeconomic Status", "title": "Influences access and effectiveness of Policy X [Marmot, 2005]"}},
        {{"id": 6, "label": "Geographical Location", "title": "Affects policy implementation and service availability [Lee et al., 2019]"}},
        {{"id": 7, "label": "Cultural Factors", "title": "Modulate response to Policy X [Garcia et al., 2018]"}},
        {{"id": 8, "label": "Public Awareness", "title": "Awareness campaigns influence effectiveness [Nguyen et al., 2021]"}}
      ],
      "edges": [
        {{"from": 1, "to": 2}},
        {{"from": 2, "to": 3}},
        {{"from": 3, "to": 4}},
        {{"from": 5, "to": 3}},
        {{"from": 6, "to": 1}},
        {{"from": 7, "to": 3}},
        {{"from": 8, "to": 3}},
        {{"from": 5, "to": 4}},
        {{"from": 6, "to": 4}},
        {{"from": 7, "to": 4}}
      ]
    }} 


**Based on the following prompt, generate a detailed directed acyclic graph (DAG) structure accounting for all the instructions above:**

Prompt: {prompt}
"""

    # Call GPT-3.5-turbo API
    response = client.chat.completions.create(
        model='gpt-3.5-turbo-0125',
        messages=[
            {'role': 'system', 'content': 'You are an AI assistant tasked with creating a Directed Acyclic Graph (DAG) based on causal relationships. Your response must be a valid JSON object with "nodes" and "edges" arrays.'},
            {'role': 'user', 'content': gpt_prompt},
            {'role': 'system', 'content': 'Remember to provide your response as a valid JSON object. Do not include any explanatory text before or after the JSON.'}
        ],
        max_tokens=2000,
        n=1,
        temperature=0.5,
    )

    # Parse the GPT response
    gpt_output = response.choices[0].message.content.strip()
    try:
        # Try to parse the JSON response
        graph_structure = json.loads(gpt_output)
        return graph_structure
    except json.JSONDecodeError as e:
        # If JSON parsing fails, return a more informative error
        raise Exception(f"Failed to parse GPT response as JSON. Error: {str(e)}. Response: {gpt_output[:200]}...")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)