import inspect

from demo_ui.main import map_freeform_intent


def test_mapper_does_not_branch_on_exact_demo_prompt_strings():
    source = inspect.getsource(map_freeform_intent)

    assert "prompt ==" not in source
    assert ".startswith(\"Summarize VendorNova risk for procurement.\")" not in source
    assert ".startswith('Summarize VendorNova risk for procurement.')" not in source
    assert "return \"VendorNova review assembled" not in source
