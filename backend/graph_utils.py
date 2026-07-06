import networkx as nx
from sqlmodel import Session, select
from typing import List, Dict, Any
from .models import Topic, TopicPrerequisiteLink

def build_topic_graph(session: Session) -> nx.DiGraph:
    """
    Queries all topics and prerequisite links from the database
    and builds a directed NetworkX graph.
    Edges are directed from Prerequisite -> Dependent.
    """
    g = nx.DiGraph()
    
    # Add all topics as nodes
    topics = session.exec(select(Topic)).all()
    for topic in topics:
        g.add_node(topic.name, id=topic.id, description=topic.description)
        
    # Query links
    links = session.exec(select(TopicPrerequisiteLink)).all()
    
    # Map topic IDs to names for easier graph operations
    id_to_name = {t.id: t.name for t in topics}
    
    # Add edges
    for link in links:
        u_name = id_to_name.get(link.prerequisite_id)
        v_name = id_to_name.get(link.topic_id)
        if u_name and v_name:
            g.add_edge(u_name, v_name)
            
    return g

def get_related_concepts(session: Session, topic_name: str) -> Dict[str, List[str]]:
    """
    Traverses the directed graph for a given topic to return:
    - prerequisites: direct nodes leading into the topic (in-neighbors)
    - dependents: direct nodes dependent on the topic (out-neighbors)
    """
    g = build_topic_graph(session)
    
    if not g.has_node(topic_name):
        return {"prerequisites": [], "dependents": []}
        
    prereqs = list(g.predecessors(topic_name))
    dependents = list(g.successors(topic_name))
    
    return {
        "prerequisites": prereqs,
        "dependents": dependents
    }

def get_all_reachable_prereqs(session: Session, topic_name: str) -> List[str]:
    """
    Returns all ancestor nodes of a topic (recursively find all prerequisites).
    """
    g = build_topic_graph(session)
    if not g.has_node(topic_name):
        return []
    # nx.ancestors returns a set of all nodes that have a path to topic_name
    return list(nx.ancestors(g, topic_name))

def get_all_reachable_dependents(session: Session, topic_name: str) -> List[str]:
    """
    Returns all descendant nodes of a topic (recursively find all dependents).
    """
    g = build_topic_graph(session)
    if not g.has_node(topic_name):
        return []
    # nx.descendants returns a set of all nodes reachable from topic_name
    return list(nx.descendants(g, topic_name))
