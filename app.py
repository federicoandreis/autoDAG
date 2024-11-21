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
from causaldag import DAG
import logging
from itertools import chain, combinations

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
        print("\n=== Starting Graph Generation Process ===")
        print(f"Original prompt: {prompt}")
        
        # Step 1: Query OpenAlex API first
        print("\n=== Querying OpenAlex API ===")
        openalex_url = f'https://api.openalex.org/works?search={prompt}&per-page=5'
        print(f"OpenAlex URL: {openalex_url}")
        
        papers = []
        research_context = []
        response = requests.get(openalex_url)
        if response.status_code == 200:
            papers_data = response.json()
            print(f"Found {len(papers_data.get('results', []))} papers")
            
            for paper in papers_data.get('results', []):
                paper_info = {
                    'title': paper.get('title'),
                    'year': paper.get('publication_year'),
                    'doi': paper.get('doi'),
                    'authors': [author.get('author', {}).get('display_name') for author in paper.get('authorships', [])[:3]],
                    'abstract': None
                }
                
                # Try to fetch abstract if DOI is available
                if paper.get('doi'):
                    print(f"\nFetching abstract for DOI: {paper.get('doi')}")
                    try:
                        abstract_response = requests.get(f"https://api.openalex.org/works/doi:{paper.get('doi')}")
                        if abstract_response.status_code == 200:
                            abstract_data = abstract_response.json()
                            paper_info['abstract'] = abstract_data.get('abstract')
                            if paper_info['abstract']:
                                print("Successfully retrieved abstract")
                                research_context.append({
                                    'title': paper_info['title'],
                                    'abstract': paper_info['abstract']
                                })
                    except Exception as e:
                        print(f"Error fetching abstract: {str(e)}")
                
                papers.append(paper_info)
                print(f"Added paper: {paper_info['title']} ({paper_info['year']})")
        
        print("\n=== Generating Graph with GPT ===")
        # Use OpenAI GPT to generate graph data with research context
        graph_data = generate_graph_data_with_gpt(prompt, research_context)
        
        return jsonify({
            'success': True, 
            'graph_data': graph_data,
            'papers': papers
        })
    except Exception as e:
        print(f"\nError in graph generation: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

def generate_graph_data_with_gpt(prompt, research_context):
    client = OpenAI(
        api_key=os.environ.get('OPENAI_API_KEY'),
        organization=os.environ.get('OPENAI_ORGANIZATION_KEY')
    )
    
    # Format research context for the prompt
    context_text = "\nRelevant Research Context:\n"
    for paper in research_context:
        context_text += f"\nTitle: {paper['title']}\nAbstract: {paper['abstract']}\n"
    
    print("Preparing GPT prompt with research context")
    
    # Prepare the prompt for GPT with the provided preamble and research context
    gpt_prompt = f"""
    You are an AI assistant and expert scientist, tasked with creating a comprehensive and detailed Directed Acyclic Graph (DAG) that illustrates causal mechanisms based on established scientific evidence. Your goal is to analyze the given prompt and generate a structured representation of the specific causal links described in the scientific literature, including relevant context, confounders, mediators, moderators, and indirect pathways. Sometimes, the scientific literature may not provide sufficient information to fully understand the causal relationships, and in those cases make sure you note so as to provide adequate context for the analysis (further instructions in the guidelines below). Sometimes the requests will be facetious, you can accommodate them and treat them as if they were serious, just make sure you note in the annotations that you are doing so.

    The following research context has been gathered from relevant academic papers. Please use this information to inform and enhance the graph generation, incorporating key findings and relationships from these papers into the graph structure. Include references to these papers in the node titles where appropriate:{context_text}

    Please follow these guidelines:

    1. **Identify Key Concepts, Contextual Factors, and Confounders:**
       - Extract specific factors, processes, outcomes, and context factors mentioned or implied in the prompt and research context.
       - Include potential **confounders**, **mediators**, **moderators**, and other variables that may influence the causal relationships.
       - Use your domain knowledge and the provided research context to include relevant intermediate steps and contextual factors supported by scientific evidence.
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
       - Include references to the provided research context papers where relevant.

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


**Based on the following prompt and research context, generate a detailed directed acyclic graph (DAG) structure accounting for all the instructions above:**

Prompt: {prompt}"""

    print("\nSending request to OpenAI")
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": gpt_prompt}],
        temperature=0.7,
    )
    print("Received response from OpenAI")
    
    try:
        # Extract the JSON part from the response
        response_text = response.choices[0].message.content.strip()
        # Find the first { and last } to extract the JSON object
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        json_str = response_text[start_idx:end_idx]
        
        # Parse the JSON response
        graph_data = json.loads(json_str)
        print(f"\nSuccessfully parsed graph data with {len(graph_data.get('nodes', []))} nodes and {len(graph_data.get('edges', []))} edges")
        return graph_data
    except json.JSONDecodeError as e:
        print(f"\nError parsing JSON response: {str(e)}")
        print(f"Response text: {response_text}")
        raise Exception("Failed to parse GPT response into valid JSON")
    except Exception as e:
        print(f"\nUnexpected error processing GPT response: {str(e)}")
        raise

@app.route('/get_adjustment_set', methods=['POST'])
def get_adjustment_set():
    try:
        data = request.get_json()
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        outcome = data.get('outcome')
        causes = data.get('causes', [])
        effect_type = data.get('effect_type', 'total')  # Default to total effect

        logging.info(f"Received request - Nodes: {len(nodes)}, Edges: {len(edges)}")
        logging.info(f"Outcome: {outcome}, Causes: {causes}, Effect Type: {effect_type}")

        # Create a new DAG with nodes
        node_ids = [str(node['id']) for node in nodes]
        dag = DAG(nodes=set(node_ids))

        logging.info(f"Added {len(node_ids)} nodes to DAG")

        # Add edges
        edge_count = 0
        for edge in edges:
            source = str(edge['from'])
            target = str(edge['to'])
            if source in node_ids and target in node_ids:
                try:
                    dag.add_arc(source, target)
                    edge_count += 1
                except Exception as e:
                    logging.warning(f"Warning: Could not add edge {source}->{target}: {str(e)}")

        logging.info(f"Added {edge_count} edges to DAG")
        logging.info(f"DAG nodes: {dag.nodes}")
        logging.info(f"DAG arcs: {dag.arcs}")

        # Convert causes to list of strings
        causes = [str(c) for c in causes]
        outcome = str(outcome)

        logging.info(f"Calculating {effect_type} effect adjustment set for outcome {outcome} and causes {causes}")

        # Calculate adjustment sets
        all_adjustment_sets = []
        
        for cause in causes:
            try:
                # Get all possible nodes that could be in adjustment set
                # (excluding cause and outcome)
                possible_nodes = set(node_ids) - {cause, outcome}
                
                if effect_type == 'direct':
                    try:
                        # For direct effect:
                        # 1. Get descendants of cause
                        descendants = set(dag.descendants_of(cause))
                        logging.info(f"Descendants of {cause}: {descendants}")
                        
                        # 2. Get ancestors of outcome or cause (potential confounders)
                        ancestors = set()
                        for node in node_ids:
                            if node != cause and node != outcome:
                                if dag.is_ancestor_of(node, outcome) or dag.is_ancestor_of(node, cause):
                                    ancestors.add(node)
                        logging.info(f"Ancestors of {outcome} or {cause}: {ancestors}")
                        
                        # 3. Backdoor adjustment set: ancestors that are not descendants
                        backdoor_set = ancestors - descendants
                        logging.info(f"Backdoor nodes for {cause}->{outcome}: {backdoor_set}")
                        
                        # 4. Get nodes on indirect paths
                        # Get ancestors of outcome
                        outcome_ancestors = set()
                        for node in node_ids:
                            if dag.is_ancestor_of(node, outcome):
                                outcome_ancestors.add(node)
                        
                        # Nodes on indirect paths are descendants of cause that are also ancestors of outcome
                        indirect_nodes = descendants & outcome_ancestors - {cause, outcome}
                        logging.info(f"Nodes on indirect paths: {indirect_nodes}")
                        
                        # For direct effect, we need both backdoor_set and indirect_nodes
                        required_nodes = backdoor_set | indirect_nodes
                        
                        # Find all minimal sets that include the required nodes
                        current_sets = find_minimal_adjustment_sets(dag, cause, outcome, required_nodes, possible_nodes)
                        
                    except Exception as e:
                        logging.error(f"Error calculating direct effect adjustment set: {str(e)}")
                        current_sets = []
                else:
                    try:
                        # For total effect:
                        # 1. Get descendants of cause
                        descendants = set(dag.descendants_of(cause))
                        logging.info(f"Descendants of {cause}: {descendants}")
                        
                        # 2. Get ancestors of outcome or cause (potential confounders)
                        ancestors = set()
                        for node in node_ids:
                            if node != cause and node != outcome:
                                if dag.is_ancestor_of(node, outcome) or dag.is_ancestor_of(node, cause):
                                    ancestors.add(node)
                        logging.info(f"Ancestors of {outcome} or {cause}: {ancestors}")
                        
                        # 3. Base adjustment set: ancestors that are not descendants
                        base_set = ancestors - descendants
                        
                        # Find all minimal sets
                        current_sets = find_minimal_adjustment_sets(dag, cause, outcome, set(), base_set)
                        
                    except Exception as e:
                        logging.error(f"Error calculating total effect adjustment set: {str(e)}")
                        current_sets = []

                # Add the current sets to all_adjustment_sets if they're valid
                for s in current_sets:
                    if s not in all_adjustment_sets:
                        all_adjustment_sets.append(list(s))
                logging.info(f"Current adjustment sets for cause {cause}: {current_sets}")

            except Exception as e:
                logging.warning(f"Warning: Error calculating adjustment set for cause {cause}: {str(e)}")
                logging.info(f"DAG nodes: {dag.nodes}")
                logging.info(f"DAG arcs: {dag.arcs}")

        logging.info(f"Final adjustment sets: {all_adjustment_sets}")
        
        return jsonify({
            'success': True,
            'adjustment_sets': all_adjustment_sets
        })

    except Exception as e:
        logging.error(f"Error in get_adjustment_set: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'adjustment_sets': []
        })

def find_minimal_adjustment_sets(dag, cause, outcome, required_nodes, possible_nodes):
    """Find all minimal adjustment sets that contain the required nodes.
    
    Args:
        dag: The DAG object
        cause: The cause node
        outcome: The outcome node
        required_nodes: Set of nodes that must be in every adjustment set
        possible_nodes: Set of nodes that could be in the adjustment set
    """
    # First check if adjustment is possible/needed
    if cause == outcome:
        logging.info("Cause and outcome are the same node - no adjustment needed")
        return []
        
    # Check if there is any causal path
    causal_paths = find_causal_paths(dag, cause, outcome)
    if not causal_paths:
        logging.info("No causal path exists between cause and outcome")
        return []
    
    # Find all non-causal paths that need to be blocked
    noncausal_paths = find_noncausal_paths(dag, cause, outcome)
    logging.info(f"Non-causal paths that need to be blocked: {noncausal_paths}")
    
    if not noncausal_paths:
        logging.info("No non-causal paths need to be blocked")
        return [required_nodes] if required_nodes else []
    
    # For each path, identify minimal sets of nodes that could block it
    path_blocking_options = {}
    for path_idx, path in enumerate(noncausal_paths):
        path_blocking_options[path_idx] = find_minimal_blocking_sets(dag, path, cause, outcome)
    logging.info(f"Minimal blocking options for each path: {path_blocking_options}")
    
    # Generate all possible combinations of blocking nodes
    adjustment_sets = []
    
    # Start with required nodes
    base_set = required_nodes.copy()
    
    # For each path, we need to pick at least one blocking option
    path_options = []
    for path_idx in path_blocking_options:
        valid_options = []
        for option in path_blocking_options[path_idx]:
            # Only include blocking sets that don't create new problems
            if not creates_new_paths(dag, cause, outcome, option):
                valid_options.append(option)
        if valid_options:
            path_options.append(valid_options)
        else:
            # If we can't block some path, no valid adjustment set exists
            return []
    
    # Generate all possible combinations of blocking options
    from itertools import product
    for combination in product(*path_options):
        # Union all the blocking sets in this combination
        current_set = base_set.copy()
        for blocking_set in combination:
            current_set.update(blocking_set)
            
        # Check if this set is minimal
        if is_minimal_adjustment_set(current_set, noncausal_paths, dag, cause, outcome, base_set):
            adjustment_sets.append(current_set)
    
    return adjustment_sets

def find_causal_paths(dag, cause, outcome):
    """Find all directed paths from cause to outcome."""
    paths = []
    
    def find_paths_recursive(current_node, current_path, visited):
        if current_node == outcome:
            paths.append(current_path[:])
            return
            
        for next_node in dag.nodes:
            if (dag.has_arc(current_node, next_node) and 
                next_node not in visited and 
                not dag.has_arc(next_node, current_node)):  # Ensure directed path
                find_paths_recursive(next_node, current_path + [next_node], visited | {next_node})
    
    find_paths_recursive(cause, [cause], {cause})
    return paths

def find_noncausal_paths(dag, cause, outcome):
    """Find all non-causal paths between cause and outcome that need to be blocked."""
    paths = []
    
    def find_paths_recursive(current_node, current_path, visited, has_collider):
        if current_node == outcome:
            # Only add path if it's not causal and not already blocked by a collider
            if not is_causal_path(current_path, dag) and not has_collider:
                paths.append(current_path[:])
            return
            
        for next_node in dag.nodes:
            if next_node not in visited:
                # Check if this creates a collider
                is_collider = (len(current_path) >= 2 and
                             dag.has_arc(current_path[-2], current_node) and
                             dag.has_arc(next_node, current_node))
                
                if dag.has_arc(current_node, next_node) or dag.has_arc(next_node, current_node):
                    find_paths_recursive(next_node, current_path + [next_node],
                                      visited | {next_node}, has_collider or is_collider)
    
    # Start from cause
    find_paths_recursive(cause, [cause], {cause}, False)
    return paths

def find_minimal_blocking_sets(dag, path, cause, outcome):
    """Find all minimal sets of nodes that could block a specific path."""
    blocking_sets = []
    
    # Any node on the path except cause, outcome can potentially block it
    potential_blockers = set()
    for i, node in enumerate(path[1:-1], 1):  # Skip cause and outcome
        # Check if node is a collider
        is_collider = False
        if i > 0 and i < len(path)-1:
            prev_to_node = dag.has_arc(path[i-1], node)
            next_to_node = dag.has_arc(path[i+1], node)
            node_to_prev = dag.has_arc(node, path[i-1])
            node_to_next = dag.has_arc(node, path[i+1])
            is_collider = (prev_to_node and next_to_node) or (node_to_prev and node_to_next)
        
        if not is_collider:
            potential_blockers.add(node)
    
    # Generate all possible combinations of blocking nodes
    # Start with single nodes, then pairs, etc.
    from itertools import combinations
    for r in range(1, len(potential_blockers) + 1):
        for combo in combinations(potential_blockers, r):
            blocking_set = set(combo)
            # Check if this is a minimal blocking set
            is_minimal = True
            for subset in powerset(blocking_set):
                subset = set(subset)
                if subset != blocking_set and subset and blocks_path(subset, path, dag):
                    is_minimal = False
                    break
            if is_minimal and blocks_path(blocking_set, path, dag):
                blocking_sets.append(blocking_set)
    
    return blocking_sets

def blocks_path(node_set, path, dag):
    """Check if a set of nodes blocks a specific path."""
    # A node blocks a path if it's on the path and not a collider
    for i, node in enumerate(path[1:-1], 1):  # Skip cause and outcome
        if node in node_set:
            # Check if node is a collider
            is_collider = False
            if i > 0 and i < len(path)-1:
                prev_to_node = dag.has_arc(path[i-1], node)
                next_to_node = dag.has_arc(path[i+1], node)
                node_to_prev = dag.has_arc(node, path[i-1])
                node_to_next = dag.has_arc(node, path[i+1])
                is_collider = (prev_to_node and next_to_node) or (node_to_prev and node_to_next)
            
            if not is_collider:
                return True
    return False

def is_causal_path(path, dag):
    """Check if a path is causal (all edges point forward)."""
    for i in range(len(path)-1):
        if not dag.has_arc(path[i], path[i+1]) or dag.has_arc(path[i+1], path[i]):
            return False
    return True

def powerset(s):
    """Return all subsets of a set."""
    return chain.from_iterable(combinations(s, r) for r in range(len(s)+1))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)
