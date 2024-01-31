# -*- coding: utf-8 -*-

from odoo import fields, models, _


class account_account(models.Model):
    _inherit = "account.account"

    excise_account = fields.Boolean("Excise Account")
