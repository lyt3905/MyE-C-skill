import os
import runpy


def keep_temporary_file(path):
    print(f"保留临时文件: {path}")


os.remove = keep_temporary_file
runpy.run_path(
    r"C:\Users\shana\.codex\skills\purchase-ledger-registration\scripts\append_purchase_row.py",
    run_name="__main__",
)
