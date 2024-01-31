# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = "res.company"

    purchase_account_id = fields.Many2one(
        "account.account", domain=[("excise_account", "=", True)]
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    purchase_account_id = fields.Many2one(
        "account.account",
        string="Purchase Excise Account",
        check_company=True,
        domain=[("excise_account", "=", True)],
        readonly=False,
        related="company_id.purchase_account_id",
    )
