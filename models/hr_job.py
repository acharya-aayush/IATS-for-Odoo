from odoo import api, fields, models


class HrJob(models.Model):
    _inherit = "hr.job"

    iats_profile_ids = fields.One2many("iats.job.profile", "job_id", string="IATS Profiles")
    iats_profile_count = fields.Integer(compute="_compute_iats_metrics")
    iats_average_score = fields.Float(compute="_compute_iats_metrics")

    @api.depends("iats_profile_ids", "iats_profile_ids.average_score")
    def _compute_iats_metrics(self):
        for job in self:
            job.iats_profile_count = len(job.iats_profile_ids)
            job.iats_average_score = sum(job.iats_profile_ids.mapped("average_score")) / len(job.iats_profile_ids) if job.iats_profile_ids else 0.0

    def _get_or_create_iats_profile(self):
        self.ensure_one()
        profile = self.sudo().iats_profile_ids[:1]
        if not profile:
            profile = self.env["iats.job.profile"].sudo().create({
                "name": f"IATS Profile - {self.name}",
                "job_id": self.id,
                "company_id": self.company_id.id or self.env.company.id,
                "minimum_degree_id": self.expected_degree.id,
            })
        return profile

    def action_open_iats_profile(self):
        self.ensure_one()
        profile = self._get_or_create_iats_profile()
        return {
            "name": "IATS Profile",
            "type": "ir.actions.act_window",
            "res_model": "iats.job.profile",
            "view_mode": "form",
            "res_id": profile.id,
            "target": "current",
        }
