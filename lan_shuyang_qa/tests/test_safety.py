import unittest
from app.agents.safety import SafetyAgent
from app.schemas import Attribution, Evidence
class SafetyTests(unittest.TestCase):
 def test_no_evidence_refuses(self):
  score, refuse, _ = SafetyAgent().evaluate([], Attribution(verdict="not_applicable", rationale="x")); self.assertEqual(score, 0); self.assertTrue(refuse)
 def test_corroborated_evidence_passes(self):
  e=[Evidence(id="1",text="x",source="CISA",score=.9,graph_paths=["APT29->T1078"]),Evidence(id="2",text="x",source="MITRE",score=.8)];score,refuse,_=SafetyAgent().evaluate(e,Attribution(verdict="supported",actor="APT29",rationale="x"));self.assertGreater(score,.55);self.assertFalse(refuse)
if __name__ == '__main__': unittest.main()
