from odoo import fields, models


class IATSScreeningKeyword(models.Model):
    _name = "iats.screening.keyword"
    _description = "IATS Screening Keyword"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    category = fields.Selection(
        [
            ("general", "General"),
            ("technical", "Technical"),
            ("behavioral", "Behavioral"),
            ("domain", "Domain"),
        ],
        default="general",
        required=True,
    )
    weight = fields.Float(default=1.0)

    _check_unique_name = models.Constraint(
        "UNIQUE(name)",
        "This keyword already exists.",
    )
