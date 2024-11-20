document.addEventListener('DOMContentLoaded', () => {
    const graphDiv = document.getElementById('graph');
    const saveProjectBtn = document.getElementById('save-project');
    const projectNameInput = document.getElementById('project-name');
    const projectsList = document.getElementById('projects-list');
    const nodeLabelInput = document.getElementById('node-label');
    const addNodeBtn = document.getElementById('add-node');
    const addEdgeBtn = document.getElementById('add-edge');
    const removeSelectedBtn = document.getElementById('remove-selected');
    const clearAllBtn = document.getElementById('clear-all');
    const suggestedNodesList = document.getElementById('suggested-nodes-list');
    const exportGraphBtn = document.getElementById('export-graph');
    const importGraphInput = document.getElementById('import-graph');
    const importGraphBtn = document.getElementById('import-graph-btn');
    const instructionsBtn = document.getElementById('instructions');
    const instructionsModal = document.getElementById('instructions-modal');
    const closeModalBtn = document.getElementsByClassName('close')[0];
    const adminPromptInput = document.getElementById('admin-prompt');
    const submitPromptBtn = document.getElementById('submit-prompt');

    let nodes = new vis.DataSet();
    let edges = new vis.DataSet();

    let network = new vis.Network(graphDiv, { nodes, edges }, {
        manipulation: {
            enabled: true,
            addEdge: function(edgeData, callback) {
                if (edgeData.from === edgeData.to) {
                    var r = confirm("Do you want to connect the node to itself?");
                    if (r === true) {
                        callback(edgeData);
                    }
                }
                else {
                    callback(edgeData);
                }
            }
        },
        edges: {
            arrows: {
                to: { enabled: true, scaleFactor: 1, type: 'arrow' }
            }
        }
    });

    function saveProject() {
        const name = projectNameInput.value;
        const content = {
            nodes: nodes.get(),
            edges: edges.get()
        };
        
        if (!name) {
            alert('Please provide a project name');
            return;
        }

        fetch('/save_project', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name, content }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Project saved successfully');
                loadProjects();
            }
        })
        .catch(error => console.error('Error:', error));
    }

    function loadProjects() {
        fetch('/get_projects')
        .then(response => response.json())
        .then(projects => {
            projectsList.innerHTML = '';
            projects.forEach(project => {
                const button = document.createElement('button');
                button.textContent = project.name;
                button.addEventListener('click', () => {
                    nodes.clear();
                    edges.clear();
                    nodes.add(project.content.nodes);
                    edges.add(project.content.edges);
                    projectNameInput.value = project.name;
                });
                projectsList.appendChild(button);
            });
        })
        .catch(error => console.error('Error:', error));
    }

    function loadSuggestedNodes() {
        fetch('/get_node_suggestions')
        .then(response => response.json())
        .then(data => {
            suggestedNodesList.innerHTML = '';
            data.nodes.forEach(node => {
                const button = document.createElement('button');
                button.textContent = node.label;
                button.title = node.annotation;
                button.addEventListener('click', () => {
                    nodes.add({ label: node.label, title: node.annotation });
                });
                suggestedNodesList.appendChild(button);
            });
        })
        .catch(error => console.error('Error:', error));
    }

    function exportGraph() {
        const graphData = {
            nodes: nodes.get(),
            edges: edges.get()
        };

        fetch('/export_graph', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(graphData),
        })
        .then(response => response.blob())
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = 'graph_export.json';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
        })
        .catch(error => console.error('Error:', error));
    }

    function importGraph(event) {
        const file = importGraphInput.files[0];
        if (file) {
            const formData = new FormData();
            formData.append('file', file);

            fetch('/import_graph', {
                method: 'POST',
                body: formData,
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    nodes.clear();
                    edges.clear();
                    nodes.add(data.content.nodes);
                    edges.add(data.content.edges);
                    alert('Graph imported successfully');
                } else {
                    alert('Error importing graph: ' + data.error);
                }
            })
            .catch(error => console.error('Error:', error));
        }
    }

    function generateGraph() {
        const prompt = adminPromptInput.value;
        if (!prompt) {
            alert('Please enter a causal link prompt');
            return;
        }

        fetch('/admin/generate_graph', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                nodes.clear();
                edges.clear();
                nodes.add(data.graph_data.nodes);
                edges.add(data.graph_data.edges);
                
                // Update related papers section
                const relatedPapersDiv = document.getElementById('related-papers');
                relatedPapersDiv.innerHTML = ''; // Clear existing papers
                
                if (data.papers && data.papers.length > 0) {
                    data.papers.forEach(paper => {
                        const paperDiv = document.createElement('div');
                        paperDiv.className = 'paper-item';
                        
                        const title = document.createElement('div');
                        title.className = 'paper-title';
                        title.textContent = paper.title;
                        
                        const authors = document.createElement('div');
                        authors.className = 'paper-authors';
                        authors.textContent = paper.authors ? paper.authors.join(', ') : 'Unknown authors';
                        
                        const year = document.createElement('div');
                        year.className = 'paper-year';
                        year.textContent = `Published: ${paper.year || 'Year unknown'}`;
                        
                        const doi = document.createElement('a');
                        doi.className = 'paper-doi';
                        if (paper.doi) {
                            doi.href = paper.doi.startsWith('http') ? paper.doi : `https://doi.org/${paper.doi}`;
                            doi.textContent = 'View Paper';
                            doi.target = '_blank';
                        }
                        
                        paperDiv.appendChild(title);
                        paperDiv.appendChild(authors);
                        paperDiv.appendChild(year);
                        if (paper.doi) {
                            paperDiv.appendChild(doi);
                        }
                        
                        relatedPapersDiv.appendChild(paperDiv);
                    });
                } else {
                    relatedPapersDiv.innerHTML = '<div class="paper-item">No related papers found.</div>';
                }
                
                alert('Graph generated successfully');
            } else {
                alert('Error generating graph: ' + data.error);
            }
        })
        .catch(error => console.error('Error:', error));
    }

    saveProjectBtn.addEventListener('click', saveProject);

    addNodeBtn.addEventListener('click', () => {
        const label = nodeLabelInput.value || 'New Node';
        nodes.add({ label: label });
        nodeLabelInput.value = '';
    });

    addEdgeBtn.addEventListener('click', () => {
        network.addEdgeMode();
    });

    removeSelectedBtn.addEventListener('click', () => {
        const selectedNodes = network.getSelectedNodes();
        const selectedEdges = network.getSelectedEdges();
        nodes.remove(selectedNodes);
        edges.remove(selectedEdges);
    });

    clearAllBtn.addEventListener('click', () => {
        nodes.clear();
        edges.clear();
    });

    exportGraphBtn.addEventListener('click', exportGraph);
    importGraphBtn.addEventListener('click', () => importGraphInput.click());
    importGraphInput.addEventListener('change', importGraph);

    // Instructions modal functionality
    instructionsBtn.addEventListener('click', () => {
        instructionsModal.style.display = 'block';
    });

    closeModalBtn.addEventListener('click', () => {
        instructionsModal.style.display = 'none';
    });

    window.addEventListener('click', (event) => {
        if (event.target == instructionsModal) {
            instructionsModal.style.display = 'none';
        }
    });

    // Right-click annotation functionality
    network.on("oncontext", function (params) {
        params.event.preventDefault();
        const nodeId = network.getNodeAt(params.pointer.DOM);
        if (nodeId) {
            const annotation = prompt('Enter annotation:');
            if (annotation) {
                const node = nodes.get(nodeId);
                const existingAnnotation = node.title || '';
                // Append the new annotation to the existing one
                node.title = existingAnnotation
                    ? existingAnnotation + '\n• ' + annotation
                    : '• ' + annotation;
                nodes.update(node);
            }
        }
    });


    // Admin generate graph functionality
    if (submitPromptBtn) {
        submitPromptBtn.addEventListener('click', generateGraph);
    }

    // Initial project and suggested nodes load
    loadProjects();
    loadSuggestedNodes();
});
