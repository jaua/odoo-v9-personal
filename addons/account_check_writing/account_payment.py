# -*- coding: utf-8 -*-

import math

from openerp import models, fields, api, _
from openerp.tools import amount_to_text_en, float_round
from openerp.exceptions import UserError, ValidationError

class account_register_payments(models.TransientModel):
    _inherit = "account.register.payments"

    check_amount_in_words = fields.Char(string="Amount in Words")
    check_manual_sequencing = fields.Boolean(related='journal_id.check_manual_sequencing')
    # Note: a check_number == 0 means that it will be attributed when the check is printed
    check_number = fields.Integer(string="Check Number", readonly=True, copy=False, default=0,
        help="Number of the check corresponding to this payment. If your pre-printed check are not already numbered, "
             "you can manage the numbering in the journal configuration page.")

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if hasattr(super(account_register_payments, self), '_onchange_journal_id'):
            super(account_register_payments, self)._onchange_journal_id()
        if self.journal_id.check_manual_sequencing:
            self.check_number = self.journal_id.check_sequence_id.number_next_actual

    @api.onchange('amount')
    def _onchange_amount(self):
        if hasattr(super(account_register_payments, self), '_onchange_amount'):
            super(account_register_payments, self)._onchange_amount()
        # TODO: merge, refactor and complete the amount_to_text and amount_to_text_en classes
        check_amount_in_words = amount_to_text_en.amount_to_text(math.floor(self.amount), lang='en', currency='')
        check_amount_in_words = check_amount_in_words.replace(' and Zero Cent', '') # Ugh
        decimals = self.amount % 1
        if decimals >= 10**-2:
            check_amount_in_words += _(' and %s/100') % str(int(round(float_round(decimals*100, precision_rounding=1))))
        self.check_amount_in_words = check_amount_in_words

    def get_payment_vals(self):
        res = super(account_register_payments, self).get_payment_vals()
        if self.payment_method == self.env.ref('account_check_writing.account_payment_method_check_writing'):
            res.update({
                'check_amount_in_words': self.check_amount_in_words,
                'check_manual_sequencing': self.check_manual_sequencing,
            })
        return res


class account_payment(models.Model):
    _inherit = "account.payment"

    check_amount_in_words = fields.Char(string="Amount in Words")
    check_manual_sequencing = fields.Boolean(related='journal_id.check_manual_sequencing')
    check_number = fields.Integer(string="Check Number", readonly=True, copy=False,
        help="The selected journal is configured to print check numbers. If your pre-printed check paper already has numbers "
             "or if the current numbering is wrong, you can change it in the journal configuration page.")

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if hasattr(super(account_payment, self), '_onchange_journal_id'):
            super(account_payment, self)._onchange_journal_id()
        if self.journal_id.check_manual_sequencing:
            self.check_number = self.journal_id.check_sequence_id.number_next_actual

    @api.onchange('amount')
    def _onchange_amount(self):
        if hasattr(super(account_payment, self), '_onchange_amount'):
            super(account_payment, self)._onchange_amount()
        check_amount_in_words = amount_to_text_en.amount_to_text(math.floor(self.amount), lang='en', currency='')
        check_amount_in_words = check_amount_in_words.replace(' and Zero Cent', '') # Ugh
        decimals = self.amount % 1
        if decimals >= 10**-2:
            check_amount_in_words += _(' and %s/100') % str(int(round(float_round(decimals*100, precision_rounding=1))))
        self.check_amount_in_words = check_amount_in_words

    def _check_communication(self, payment_method_id, communication):
        super(account_payment, self)._check_communication(payment_method_id, communication)
        if payment_method_id == self.env.ref('account_check_writing.account_payment_method_check_writing').id:
            if not communication:
                return
            if len(communication) > 60:
                raise ValidationError(_("A check memo cannot exceed 60 characters."))

    @api.model
    def create(self, vals):
        if vals['payment_method'] == self.env.ref('account_check_writing.account_payment_method_check_writing').id\
                and vals.get('check_manual_sequencing'):
            sequence = self.env['account.journal'].browse(vals['journal_id']).check_sequence_id
            vals.update({'check_number': sequence.next_by_id()})
        return super(account_payment, self.sudo()).create(vals)

    @api.multi
    def send_checks(self):
        """ Check that the recordset is valid, set the payments state to sent and call print_checks() """
        # Since this method can be called via a client_action_multi, we need to make sure the received records are what we expect
        self = self.filtered(lambda r: r.payment_method.code == 'check_writing' and r.state != 'reconciled')

        if len(self) == 0:
            raise UserError(_("Payments to print as a checks must have 'Check Writing' selected as payment method and "
                              "not have already been reconciled"))
        if any(payment.journal_id != self[0].journal_id for payment in self):
            raise UserError(_("In order to print multiple checks at once, they must belong to the same bank journal."))

        self.filtered(lambda r: r.state == 'draft').post()
        self.write({'state': 'sent'})

        return self.print_checks()

    @api.multi
    def print_checks(self):
        """ This method is a hook for l10n_xx_check_printing modules to implement actual check printing capabilities """
        pass