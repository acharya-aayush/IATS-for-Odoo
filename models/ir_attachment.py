from odoo import api, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        applicant_ids = [
            attachment.res_id
            for attachment in attachments
            if attachment.res_model == "hr.applicant" and attachment.res_id and not attachment.res_field
        ]
        if applicant_ids:
            applicants = self.env["hr.applicant"].sudo().browse(applicant_ids).exists()
            for applicant in applicants:
                applicant._reset_iats_scores()
                applicant._after_iats_resume_change()
        return attachments
