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
        nodes: {
            color: {
                background: '#D2E5FF',
                border: '#2B7CE9',
                highlight: {
                    background: '#D2E5FF',
                    border: '#2B7CE9'
                }
            }
        },
        edges: {
            arrows: {
                to: { enabled: true, scaleFactor: 1, type: 'arrow' }
            },
            smooth: {
                type: 'continuous'
            }
        },
        physics: {
            enabled: true,
            barnesHut: {
                gravitationalConstant: -2000,
                centralGravity: 0.3,
                springLength: 95,
                springConstant: 0.04,
                damping: 0.09
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

    // Function to update node colors based on current selection and adjustment set
    function updateNodeColors(adjustmentSet = []) {
        console.log('Updating colors with adjustment set:', adjustmentSet);
        
        const outcomeNode = document.getElementById('outcome-select').value;
        const causeNodes = Array.from(document.getElementById('causes-select').selectedOptions).map(option => option.value);
        
        console.log('Outcome:', outcomeNode);
        console.log('Causes:', causeNodes);
        
        // Get all nodes
        const allNodes = nodes.get();
        const updates = [];
        
        // First set all nodes to default color
        allNodes.forEach(node => {
            updates.push({
                id: node.id,
                color: {
                    background: '#D2E5FF',
                    border: '#2B7CE9'
                }
            });
        });
        
        // Then color adjustment set nodes red
        if (adjustmentSet && adjustmentSet.length > 0) {
            adjustmentSet.forEach(nodeId => {
                if (!causeNodes.includes(nodeId) && nodeId !== outcomeNode) {
                    updates.push({
                        id: nodeId,
                        color: {
                            background: '#FFCDD2',
                            border: '#F44336'
                        }
                    });
                }
            });
        }
        
        // Then color cause nodes green
        causeNodes.forEach(nodeId => {
            updates.push({
                id: nodeId,
                color: {
                    background: '#A5D6A7',
                    border: '#4CAF50'
                }
            });
        });
        
        // Finally color outcome node blue (unless it's also a cause)
        if (outcomeNode && !causeNodes.includes(outcomeNode)) {
            updates.push({
                id: outcomeNode,
                color: {
                    background: '#97C2FC',
                    border: '#2B7CE9'
                }
            });
        }
        
        // Apply all updates at once
        if (updates.length > 0) {
            console.log('Applying color updates:', updates);
            nodes.update(updates);
        }
    }

    // Add event listener for adjustment set calculation
    document.getElementById('get-adjustment-set').addEventListener('click', () => {
        console.log('Get adjustment set clicked');
        const outcomeSelect = document.getElementById('outcome-select');
        const causesSelect = document.getElementById('causes-select');
        const effectTypeSelect = document.getElementById('effect-type');
        const adjustmentSetDisplay = document.getElementById('adjustment-set-display');

        const outcome = outcomeSelect.value;
        const causes = Array.from(causesSelect.selectedOptions).map(option => option.value);
        const effectType = effectTypeSelect.value;

        if (!outcome || causes.length === 0) {
            alert('Please select both outcome and at least one cause');
            return;
        }

        // Reset display
        adjustmentSetDisplay.textContent = 'Calculating...';

        fetch('/get_adjustment_set', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                nodes: nodes.get(),
                edges: edges.get(),
                outcome: outcome,
                causes: causes,
                effect_type: effectType
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const adjustmentSets = data.adjustment_sets;
                console.log('Received adjustment sets:', adjustmentSets);
                
                if (adjustmentSets.length > 0) {
                    // Get node labels for display
                    const nodeLabels = adjustmentSets[0].map(nodeId => {
                        const node = nodes.get(nodeId);
                        return node ? (node.label || nodeId) : nodeId;
                    });
                    
                    adjustmentSetDisplay.textContent = `Adjustment Set: {${nodeLabels.join(', ')}}`;
                    
                    // Update colors with the adjustment set
                    updateNodeColors(adjustmentSets[0]);
                } else {
                    adjustmentSetDisplay.textContent = 'No adjustment set needed';
                    updateNodeColors([]);
                }
            } else {
                console.error('Error:', data.error);
                adjustmentSetDisplay.textContent = 'Error: ' + data.error;
                updateNodeColors([]);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            adjustmentSetDisplay.textContent = 'Error calculating adjustment set';
            updateNodeColors([]);
        });
    });

    // Remove the automatic color updates on selection changes
    document.getElementById('outcome-select').removeEventListener('change', updateNodeColors);
    document.getElementById('causes-select').removeEventListener('change', updateNodeColors);
    document.getElementById('effect-type').removeEventListener('change', updateNodeColors);

    // Update selectors when nodes change
    nodes.on('*', () => {
        updateNodeSelectors();
    });

    function updateNodeSelectors() {
        const outcomeSelect = document.getElementById('outcome-select');
        const causesSelect = document.getElementById('causes-select');
        
        // Store current selections
        const currentOutcome = outcomeSelect.value;
        const currentCauses = Array.from(causesSelect.selectedOptions).map(opt => opt.value);
        
        // Clear and repopulate options
        outcomeSelect.innerHTML = '<option value="">Select Outcome</option>';
        causesSelect.innerHTML = '';
        
        nodes.get().forEach(node => {
            const outcomeOpt = document.createElement('option');
            outcomeOpt.value = node.id;
            outcomeOpt.text = node.label || node.id;
            outcomeSelect.appendChild(outcomeOpt.cloneNode(true));
            causesSelect.appendChild(outcomeOpt);
        });
        
        // Restore selections if nodes still exist
        if (currentOutcome && nodes.get(currentOutcome)) {
            outcomeSelect.value = currentOutcome;
        }
        currentCauses.forEach(value => {
            if (nodes.get(value)) {
                const option = causesSelect.querySelector(`option[value="${value}"]`);
                if (option) option.selected = true;
            }
        });
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
