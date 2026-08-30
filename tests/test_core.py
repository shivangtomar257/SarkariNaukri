from portal.pipeline.classify import classify
from portal.pipeline.dedupe import normalized_key, similarity

def test_classification():
    assert classify("Recruitment Advertisement", "Applications are invited for 100 vacancies")[0] == "job"
    assert classify("Admit Card", "Download hall ticket")[0] == "admit_card"
    assert classify("Final Result", "Merit list result declared")[0] == "result"

def test_dedupe_key_stable():
    assert normalized_key("SSC CGL Recruitment", "2026") == normalized_key("SSC CGL Recruitment", "2026")
    assert similarity("RRB Junior Engineer Recruitment", "RRB Junior Engineer Recruitment 2026") > 0.8
