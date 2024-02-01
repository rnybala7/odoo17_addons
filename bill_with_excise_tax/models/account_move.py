# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from contextlib import ExitStack, contextmanager
from odoo.exceptions import UserError


class account_move(models.Model):
    _inherit = "account.move"

    invoice_line_ids = fields.One2many(
        "account.move.line",
        "move_id",
        string="Invoice lines",
        copy=False,
        readonly=True,
        domain=[
            ("display_type", "in", ("product", "line_section", "line_note")),
            ("exclude_from_invoice_tab", "=", False),
        ],
    )

    def _calculate_excise(self):
        res = 0.0
        for move in self:
            line_excise = 0.0
            for line in move.invoice_line_ids:
                line_excise += line.excise_amount
        res = line_excise
        return res

    @api.depends(
        "line_ids.matched_debit_ids.debit_move_id.move_id.payment_id.is_matched",
        "line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual",
        "line_ids.matched_debit_ids.debit_move_id.move_id.line_ids.amount_residual_currency",
        "line_ids.matched_credit_ids.credit_move_id.move_id.payment_id.is_matched",
        "line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual",
        "line_ids.matched_credit_ids.credit_move_id.move_id.line_ids.amount_residual_currency",
        "line_ids.balance",
        "line_ids.currency_id",
        "line_ids.amount_currency",
        "line_ids.amount_residual",
        "line_ids.amount_residual_currency",
        "line_ids.payment_id.state",
        "line_ids.full_reconcile_id",
    )
    def _compute_amount(self):
        for move in self:
            res_config = self.env.company
            total_untaxed, total_untaxed_currency = 0.0, 0.0
            total_tax, total_tax_currency = 0.0, 0.0
            total_residual, total_residual_currency = 0.0, 0.0
            total, total_currency = 0.0, 0.0

            for line in move.line_ids:
                if move.is_invoice(True):
                    # === Invoices ===
                    if line.display_type == "tax" or (
                        line.display_type == "rounding" and line.tax_repartition_line_id
                    ):
                        # Tax amount.
                        total_tax += line.balance
                        total_tax_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.display_type in ("product", "rounding"):
                        # Untaxed amount.
                        total_untaxed += line.balance
                        total_untaxed_currency += line.amount_currency
                        total += line.balance
                        total_currency += line.amount_currency
                    elif line.display_type == "payment_term":
                        # Residual amount.
                        total_residual += line.amount_residual
                        total_residual_currency += line.amount_residual_currency
                else:
                    # === Miscellaneous journal entry ===
                    if line.debit:
                        total += line.balance
                        total_currency += line.amount_currency

            sign = move.direction_sign
            move.amount_untaxed = sign * total_untaxed_currency
            move.amount_tax = sign * total_tax_currency
            move.amount_total = sign * total_currency
            move.amount_residual = -sign * total_residual_currency

            move.amount_untaxed_signed = -total_untaxed
            move.amount_tax_signed = -total_tax
            move.amount_total_signed = (
                abs(total) if move.move_type == "entry" else -total
            )
            move.amount_residual_signed = total_residual
            move.amount_total_in_currency_signed = (
                abs(move.amount_total)
                if move.move_type == "entry"
                else -(sign * move.amount_total)
            )
            res = move._calculate_excise()
            move.excise_amt = res
            move.excise_amt_line = res

            if move.excise_amt_line or move.excise_amt:
                if move.move_type in ["in_invoice", "in_receipt", "in_refund"]:
                    if res_config.purchase_account_id:
                        move.excise_account_id = res_config.purchase_account_id.id
                    else:
                        raise UserError(
                            _("Please define an excise tax account for this company.")
                        )
                    move.excise_account_id = res_config.purchase_account_id.id

    def _compute_amount_account(self):
        for record in self:
            for line in record.invoice_line_ids:
                if line.product_id:
                    record.excise_account_id = line.account_id.id

    amount_untaxed = fields.Monetary(
        string="Untaxed Amount",
        compute="_compute_amount",
        store=True,
        readonly=True,
        tracking=True,
    )
    amount_tax = fields.Monetary(
        string="Tax",
        compute="_compute_amount",
        store=True,
        readonly=True,
    )
    amount_total = fields.Monetary(
        string="Total",
        compute="_compute_amount",
        store=True,
        readonly=True,
        inverse="_inverse_amount_total",
    )
    excise_amt = fields.Monetary(
        string="Excise", readonly=True, compute_sudo="_compute_amount"
    )
    excise_account_id = fields.Many2one(
        "account.account", "Excise Account", compute="_compute_amount_account"
    )
    excise_amt_line = fields.Monetary(
        compute_sudo="_compute_amount", string="Excise Amount", readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        result = super(account_move, self).create(vals_list)
        res_config = self.env.company
        for res in result:

            if res.state in "draft":
                account = False
                for line in res.invoice_line_ids:
                    if line.product_id:

                        account = line.account_id.id

                l = res.line_ids.filtered(lambda s: s.name == "Excise Tax")

                if len(l or []) == 0 and account:

                    excise_vals = {
                        "account_id": res_config.purchase_account_id.id,
                        "quantity": 1,
                        "price_unit": res.excise_amt_line,
                        "name": "Excise Tax",
                        "tax_ids": None,
                        "exclude_from_invoice_tab": True,
                        "display_type": "product",
                    }
                    res.with_context(check_move_validity=False).write(
                        {"invoice_line_ids": [(0, 0, excise_vals)]}
                    )
        return result

    @contextmanager
    def _sync_dynamic_lines(self, container):

        with self._disable_recursion(container, "skip_invoice_sync") as disabled:
            if disabled:
                yield
                return

            def update_containers():
                tax_container["records"] = container["records"].filtered(
                    lambda m: (
                        m.is_invoice(True)
                        or m.line_ids.tax_ids
                        and not m.tax_cash_basis_origin_move_id
                    )
                )
                invoice_container["records"] = container["records"].filtered(
                    lambda m: m.is_invoice(True)
                )
                misc_container["records"] = container["records"].filtered(
                    lambda m: m.move_type == "entry"
                    and not m.tax_cash_basis_origin_move_id
                )

            tax_container, invoice_container, misc_container = ({} for __ in range(3))
            update_containers()
            with ExitStack() as stack:
                stack.enter_context(
                    self._sync_dynamic_line(
                        existing_key_fname="term_key",
                        needed_vals_fname="needed_terms",
                        needed_dirty_fname="needed_terms_dirty",
                        line_type="payment_term",
                        container=invoice_container,
                    )
                )
                stack.enter_context(self._sync_unbalanced_lines(misc_container))
                stack.enter_context(self._sync_rounding_lines(invoice_container))
                stack.enter_context(
                    self._sync_dynamic_line(
                        existing_key_fname="tax_key",
                        needed_vals_fname="line_ids.compute_all_tax",
                        needed_dirty_fname="line_ids.compute_all_tax_dirty",
                        line_type="tax",
                        container=tax_container,
                    )
                )
                stack.enter_context(
                    self._sync_dynamic_line(
                        existing_key_fname="epd_key",
                        needed_vals_fname="line_ids.epd_needed",
                        needed_dirty_fname="line_ids.epd_dirty",
                        line_type="epd",
                        container=invoice_container,
                    )
                )
                stack.enter_context(self._sync_invoice(invoice_container))
                line_container = {"records": self.line_ids}

                with self.line_ids._sync_invoice(line_container):
                    yield
                    line_container["records"] = self.line_ids

                    def find_excise_line(line_container):
                        return line_container["records"].filtered(
                            lambda line: line.name == "Excise Tax"
                        )

                    excise_line = find_excise_line(line_container)
                    for move in self:
                        res = self._calculate_excise()
                        if excise_line:
                            new_debit_value = res
                            excise_line.write({"debit": new_debit_value})

                update_containers()
