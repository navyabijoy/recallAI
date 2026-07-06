from sqlmodel import Session, create_engine, SQLModel
from backend.models import Topic, TopicPrerequisiteLink
from backend.graph_utils import build_topic_graph, get_related_concepts, get_all_reachable_prereqs

def test_graph_construction_and_traversal():
    # Use in-memory sqlite engine for tests
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        # Create topics
        t_a = Topic(name="A", description="Topic A")
        t_b = Topic(name="B", description="Topic B")
        t_c = Topic(name="C", description="Topic C")
        session.add(t_a)
        session.add(t_b)
        session.add(t_c)
        session.commit()
        
        session.refresh(t_a)
        session.refresh(t_b)
        session.refresh(t_c)
        
        # Link prerequisites: A -> B, B -> C
        link_ab = TopicPrerequisiteLink(topic_id=t_b.id, prerequisite_id=t_a.id)
        link_bc = TopicPrerequisiteLink(topic_id=t_c.id, prerequisite_id=t_b.id)
        session.add(link_ab)
        session.add(link_bc)
        session.commit()
        
        # Test direct connections
        relations_b = get_related_concepts(session, "B")
        assert relations_b["prerequisites"] == ["A"]
        assert relations_b["dependents"] == ["C"]
        
        # Test full ancestors
        ancestors_c = get_all_reachable_prereqs(session, "C")
        assert set(ancestors_c) == {"A", "B"}
        
        # Test networkx object directly
        g = build_topic_graph(session)
        assert g.has_node("A")
        assert g.has_edge("A", "B")
        assert g.has_edge("B", "C")
