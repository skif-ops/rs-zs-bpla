from __future__ import annotations
import pandas as pd
from ml.type_readiness import assess_type_readiness


def test_confirmed_lutyi_and_weak_fp1_are_research_only():
    rows=[]
    for i in range(6):
        rows.append({"label":"Лютый","source_file":f"l{i}","meta_label_confidence":"confirmed","meta_dataset_role":"training_provisional","meta_validation_eligible":False})
    for i in range(3):
        rows.append({"label":"FP-1","source_file":f"f{i}","meta_label_confidence":"weak","meta_dataset_role":"training_provisional_weak","meta_validation_eligible":False})
    ready=assess_type_readiness(pd.DataFrame(rows),("Лютый","FP-1"))
    assert ready.research_ready is True
    assert ready.confirmed_contrast_ready is False
    assert ready.operational_validation_ready is False
    assert ready.mode == "weak_contrast_research_only"


def test_multiple_files_in_one_source_group_count_once():
    rows = [
        {
            "label": "Лютый",
            "source_file": f"view-{index}.wav",
            "meta_source_group": "same-flight",
            "meta_label_confidence": "confirmed",
            "meta_dataset_role": "training_provisional",
            "meta_validation_eligible": False,
        }
        for index in range(3)
    ]

    ready = assess_type_readiness(pd.DataFrame(rows), ("Лютый",))

    assert ready.labels[0].total_sources == 1
    assert ready.labels[0].confirmed_sources == 1
