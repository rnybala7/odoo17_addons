# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from odoo.tools import frozendict


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    excise_amount = fields.Float("Excise Amount")
    excise_amt = fields.Float("Excise Final Amount")
    exclude_from_invoice_tab = fields.Boolean(
        help="Technical field used to exclude some lines from the invoice_line_ids tab in the form view."
    )

    @api.depends(
        "tax_ids",
        "currency_id",
        "partner_id",
        "analytic_distribution",
        "balance",
        "partner_id",
        "move_id.partner_id",
        "price_unit",
    )
    def _compute_all_tax(self):
        for line in self:
            sign = line.move_id.direction_sign
            if line.display_type == "tax":
                line.compute_all_tax = {}
                line.compute_all_tax_dirty = False
                continue
            if line.display_type == "product" and line.move_id.is_invoice(True):
                if line.move_type in ["in_invoice", "in_receipt", "in_refund"]:
                    amount_currency = sign * (line.price_unit + line.excise_amount)
                else:
                    amount_currency = sign * line.price_unit
                handle_price_include = True
                quantity = line.quantity
            else:
                amount_currency = line.amount_currency
                handle_price_include = False
                quantity = 1
            compute_all_currency = line.tax_ids.compute_all(
                amount_currency,
                currency=line.currency_id,
                quantity=quantity,
                product=line.product_id,
                partner=line.move_id.partner_id or line.partner_id,
                is_refund=line.is_refund,
                handle_price_include=handle_price_include,
                include_caba_tags=line.move_id.always_tax_exigible,
                fixed_multiplicator=sign,
            )
            rate = line.amount_currency / line.balance if line.balance else 1
            line.compute_all_tax_dirty = True
            line.compute_all_tax = {
                frozendict(
                    {
                        "tax_repartition_line_id": tax["tax_repartition_line_id"],
                        "group_tax_id": tax["group"] and tax["group"].id or False,
                        "account_id": tax["account_id"] or line.account_id.id,
                        "currency_id": line.currency_id.id,
                        "analytic_distribution": (
                            tax["analytic"] or not tax["use_in_tax_closing"]
                        )
                        and line.analytic_distribution,
                        "tax_ids": [(6, 0, tax["tax_ids"])],
                        "tax_tag_ids": [(6, 0, tax["tag_ids"])],
                        "partner_id": line.move_id.partner_id.id or line.partner_id.id,
                        "move_id": line.move_id.id,
                        "display_type": line.display_type,
                    }
                ): {
                    "name": tax["name"],
                    "balance": tax["amount"] / rate,
                    "amount_currency": tax["amount"],
                    "tax_base_amount": tax["base"]
                    / rate
                    * (-1 if line.tax_tag_invert else 1),
                }
                for tax in compute_all_currency["taxes"]
                if tax["amount"]
            }
            if not line.tax_repartition_line_id:
                line.compute_all_tax[frozendict({"id": line.id})] = {
                    "tax_tag_ids": [(6, 0, compute_all_currency["base_tags"])],
                }

    def _convert_to_tax_base_line_dict(self):
        """Convert the current record to a dictionary in order to use the generic taxes computation method
        defined on account.tax.
        :return: A python dictionary.
        """
        self.ensure_one()
        is_invoice = self.move_id.is_invoice(include_receipts=True)
        sign = -1 if self.move_id.is_inbound(include_receipts=True) else 1
        if sign == 1:
            return self.env["account.tax"]._convert_to_tax_base_line_dict(
                self,
                partner=self.partner_id,
                currency=self.currency_id,
                product=self.product_id,
                taxes=self.tax_ids,
                price_unit=self.price_unit + self.excise_amount
                if is_invoice
                else self.amount_currency,
                quantity=self.quantity if is_invoice else 1.0,
                discount=self.discount if is_invoice else 0.0,
                account=self.account_id,
                analytic_distribution=self.analytic_distribution,
                price_subtotal=sign * self.amount_currency,
                is_refund=self.is_refund,
                rate=(abs(self.amount_currency) / abs(self.balance))
                if self.balance
                else 1.0,
            )
        else:
            return self.env["account.tax"]._convert_to_tax_base_line_dict(
                self,
                partner=self.partner_id,
                currency=self.currency_id,
                product=self.product_id,
                taxes=self.tax_ids,
                price_unit=self.price_unit if is_invoice else self.amount_currency,
                quantity=self.quantity if is_invoice else 1.0,
                discount=self.discount if is_invoice else 0.0,
                account=self.account_id,
                analytic_distribution=self.analytic_distribution,
                price_subtotal=sign * self.amount_currency,
                is_refund=self.is_refund,
                rate=(abs(self.amount_currency) / abs(self.balance))
                if self.balance
                else 1.0,
            )
