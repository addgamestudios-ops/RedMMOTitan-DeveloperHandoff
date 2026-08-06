"""R77 exact-coast verifier wrapper with corrected inherited namespace routing."""

from pathlib import Path


SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\audit_redmmo_profile_v1_oasis_water_r76.py")
text = SOURCE.read_text(encoding="utf-8")
text = text.replace("R76", "R77").replace("r76", "r77")
text = text.replace("20260806T0026Z", "20260806T0051Z")
text = text.replace(
    "F733E34812872D5E0986DB9DAB6B7D61EA06E2FDCBC31DF99AC592BC2ED37F5B",
    "76EDB666C7DF6858128CC01CE2481871589DC9319B74C86050316E32D93BD09C",
)
text = text.replace(
    "62A00B4FF41BDB9C88907126C76D54C05595E17841355FFDF804C8B5AB7E4250",
    "6448A378C02DC1EE6FEF9E77671B71930A7F84ACD9F279352987F43E4F8D629E",
)
text = text.replace(
    "3B0AAFB59A2DD7DD65709958F7ACDE6A27C73A0CBEA1991B8EE04B992A2A3687",
    "744464E525DFF20BD0396BBC073F8086C8C9784006C2516FB135E5DBDC0DF498",
)
text = text.replace('ns["now"]', 'base_ns["now"]')
text = text.replace('ns["provider_gate"]', 'base_ns["provider_gate"]')
text = text.replace('ns["write_json_exclusive"]', 'base_ns["write_json_exclusive"]')

exec(compile(text, str(SOURCE), "exec"), {"__name__": "__main__", "__file__": str(SOURCE)})
