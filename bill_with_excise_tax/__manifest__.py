# -*- coding: utf-8 -*-
{
    "name": "Vendor Bill with Excise Tax",
    "version": "17.0.0.0",
    "category": "Invoicing",
    "sequence": 11,
    "summary": "Vendor bill with Excise Tax",
    "description": """
Vendor bill with Excise Tax
""",
    "author": "Rinoy",
    "depends": ["base", "account"],
    "data": [
        "views/account_account.xml",
        "views/res_config_settings.xml",
        "views/invoice_view.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
}
