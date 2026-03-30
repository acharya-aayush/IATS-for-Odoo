import re
import logging
import numpy as np

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

nlp = None





class IATSJobProfile(models.Model):
    _name = "iats.job.profile"
    _description = "IATS Job Profile"
    _order = "write_date desc, id desc"

    seniority_level = fields.Selection([
        ('intern', 'Intern / Entry (No Impact Expected)'),
        ('junior', 'Junior (Light Impact)'),
        ('mid', 'Mid-Level (Standard)'),
        ('senior', 'Senior / Elite (High Impact)')
    ], string="Position Seniority", default='mid')
    anti_fluff_enabled = fields.Boolean(string="Anti-Fluff Metric Check", default=True, help="Penalizes meaningless metrics like 'achieved 90% efficiency' without stating the underlying technology or business context.")

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    job_id = fields.Many2one("hr.job", required=True, ondelete="cascade", index=True)
    keyword_ids = fields.Many2many("iats.screening.keyword", string="Priority Keywords")
    minimum_years_experience = fields.Float(default=0.0)
    minimum_degree_id = fields.Many2one("hr.recruitment.degree", string="Minimum Degree")
    minimum_score = fields.Float(default=70.0)

    auto_screen_enabled = fields.Boolean(default=True)
    auto_move_stage = fields.Boolean(default=False)
    auto_notify_reviewers = fields.Boolean(default=False)
    reviewer_user_ids = fields.Many2many("res.users", string="Reviewers")
    shortlist_stage_id = fields.Many2one("hr.recruitment.stage", string="Shortlist Stage")
    review_stage_id = fields.Many2one("hr.recruitment.stage", string="Review Stage")
    reject_stage_id = fields.Many2one("hr.recruitment.stage", string="Reject Stage")

    keyword_weight = fields.Float(default=30.0)
    skill_weight = fields.Float(default=25.0)
    experience_weight = fields.Float(default=20.0)
    education_weight = fields.Float(default=10.0)
    completeness_weight = fields.Float(default=15.0)
    total_weight = fields.Float(compute="_compute_total_weight")

    applicant_ids = fields.One2many("hr.applicant", "iats_profile_id", string="Applicants")
    applicant_count = fields.Integer(compute="_compute_dashboard_metrics")
    screened_count = fields.Integer(compute="_compute_dashboard_metrics")
    high_match_count = fields.Integer(compute="_compute_dashboard_metrics")
    average_score = fields.Float(compute="_compute_dashboard_metrics")

    _check_unique_job = models.Constraint(
        "UNIQUE(job_id)",
        "Each job can only have one IATS profile.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") and vals.get("job_id"):
                job = self.env["hr.job"].browse(vals["job_id"])
                vals["name"] = f"IATS Profile - {job.name}"
            vals.setdefault("company_id", self.env.company.id)
        return super().create(vals_list)

    @api.depends(
        "keyword_weight",
        "skill_weight",
        "experience_weight",
        "education_weight",
        "completeness_weight",
    )
    def _compute_total_weight(self):
        for profile in self:
            profile.total_weight = (
                profile.keyword_weight
                + profile.skill_weight
                + profile.experience_weight
                + profile.education_weight
                + profile.completeness_weight
            )

    @api.depends("applicant_ids", "applicant_ids.iats_score", "applicant_ids.iats_state")
    def _compute_dashboard_metrics(self):
        for profile in self:
            applicants = profile.applicant_ids
            scored = applicants.filtered(lambda applicant: applicant.iats_state == "scored")
            profile.applicant_count = len(applicants)
            profile.screened_count = len(scored)
            profile.high_match_count = len(scored.filtered(lambda applicant: applicant.iats_score >= profile.minimum_score))
            profile.average_score = sum(scored.mapped("iats_score")) / len(scored) if scored else 0.0

    def _normalize_weights(self):
        self.ensure_one()
        total = self.total_weight or 100.0
        return {
            "keyword": (self.keyword_weight / total) * 100.0,
            "skill": (self.skill_weight / total) * 100.0,
            "experience": (self.experience_weight / total) * 100.0,
            "education": (self.education_weight / total) * 100.0,
            "completeness": (self.completeness_weight / total) * 100.0,
        }

    def _collect_keywords(self):
        self.ensure_one()
        keyword_map = {}

        for keyword in self.keyword_ids:
            keyword_map[keyword.name.strip().lower()] = max(keyword.weight, keyword_map.get(keyword.name.strip().lower(), 0.0))

        if self.job_id.name:
            keyword_map.setdefault(self.job_id.name.strip().lower(), 1.0)

        description = re.sub(r"<[^>]+>", " ", self.job_id.description or "").lower()
        for token in re.findall(r"[a-z0-9][a-z0-9.+#-]{2,}", description):
            keyword_map.setdefault(token, 0.5)

        return keyword_map

    def _extract_years_from_text(self, resume_text):
        values = []
        for match in re.findall(r"(\d+(?:\.\d+)?)\+?\s+years?", resume_text.lower()):
            try:
                values.append(float(match))
            except ValueError:
                continue
        return max(values) if values else 0.0

    def _score_skills(self, applicant):
        self.ensure_one()
        job_skills = getattr(self.job_id, "job_skill_ids", self.env["hr.job.skill"])
        applicant_skills = getattr(applicant, "current_applicant_skill_ids", self.env["hr.applicant.skill"])
        if not job_skills:
            return 100.0 if applicant_skills else 60.0

        applicant_skill_map = {skill.skill_id.id: skill.level_progress or 0.0 for skill in applicant_skills}
        score_parts = []
        resume_text_lower = applicant.iats_resume_text.lower() if applicant.iats_resume_text else ""
        for job_skill in job_skills:
            required = max(job_skill.level_progress or 0.0, 1.0)
            actual = applicant_skill_map.get(job_skill.skill_id.id, -1.0)
            
            if actual < 0:
                # Text-based semantic fallback checking
                skill_name = job_skill.skill_id.name.lower()
                if skill_name in resume_text_lower:
                    actual = required  # Assume they have it if it's explicitly mentioned
                else:
                    actual = 0.0
                    
            score_parts.append(min(actual / required, 1.0))
        return (sum(score_parts) / len(score_parts)) * 100.0 if score_parts else 0.0

    def _extract_education_from_text(self, resume_text):
        if not resume_text:
            return 0.0
            
        text = resume_text.lower()
        # High value/PhD
        phd_patterns = ['phd', 'ph.d', 'doctorate', 'doctoral']
        if any(p in text for p in phd_patterns):
            return 100.0
            
        # Master Degree
        master_patterns = ['master', 'msc', 'm.sc', 'm.a', 'ma ', 'mba', 'm.b.a']
        if any(re.search(r'\b%s\b' % p, text) for p in master_patterns):
            return 80.0
            
        # Bachelor Degree
        bachelor_patterns = ['bachelor', 'bsc', 'b.sc', 'b.a', 'ba ', 'b.e', 'btech', 'b.tech', 'bit', 'b.i.t', 'bbs', 'b.b.s', 'bca', 'b.c.a']
        if any(re.search(r'\b%s\b' % p, text) for p in bachelor_patterns):
            return 60.0
            
        return 0.0

    def _score_education(self, applicant):
        self.ensure_one()
        if not self.minimum_degree_id:
            return 100.0

        minimum_score = getattr(self.minimum_degree_id, "score", 60.0) or 60.0
        
        # Priority 1: Official Odoo Field mapping
        applicant_score = getattr(applicant.type_id, "score", 0.0)
        
        # Priority 2: Use AI NLP Extraction from Text!
        if applicant_score <= 0 and applicant.iats_resume_text:
            applicant_score = self._extract_education_from_text(applicant.iats_resume_text)

        if applicant_score >= minimum_score:
            return 100.0
        if minimum_score <= 0:
            return 50.0
            
        return max((applicant_score / minimum_score) * 100.0, 0.0)

    def _score_completeness(self, applicant):
        checks = [
            bool(applicant.partner_name),
            bool(applicant.email_from),
            bool(applicant.partner_phone),
            bool(applicant.linkedin_profile),
            bool(applicant.type_id),
            bool(applicant.iats_resume_text),
        ]
        return (sum(1 for item in checks if item) / len(checks)) * 100.0

    def _build_recommendation(self, total_score):
        self.ensure_one()
        if total_score >= self.minimum_score + 15:
            return "shortlist"
        if total_score >= self.minimum_score:
            return "review"
        return "reject"

    def _score_applicant(self, applicant):
        self.ensure_one()
        if applicant.iats_resume_parse_status != "ready" or not applicant.iats_resume_text:
            raise UserError("The applicant resume is not ready for IATS screening yet.")

        normalized_weights = self._normalize_weights()
        resume_text = applicant.iats_resume_text.lower()
        
        keyword_score = 0.0
        matched_keywords = []
        summary_details = []
        
        # 1. Semantic Embedding Similarity
        semantic_sim = 0.0
        try:
            from sentence_transformers import SentenceTransformer
            sentence_model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
        except Exception as e:
            sentence_model = None
            _logger.warning(f"Failed to locally load model: {e}")

        if sentence_model and resume_text and self.job_id.description:
            try:
                job_desc = re.sub(r"<[^>]+>", " ", self.job_id.description or "").strip()
                if len(job_desc) > 50:
                    emb_resume = sentence_model.encode(resume_text[:2000])
                    emb_job = sentence_model.encode(job_desc[:2000])
                    semantic_sim = float(np.dot(emb_resume, emb_job) / (np.linalg.norm(emb_resume) * np.linalg.norm(emb_job)))
                    semantic_sim = min(max((semantic_sim - 0.3) * 150, 0.0), 100.0)
            except Exception as e:
                _logger.error(f"Semantic model failed: {e}")
            finally:
                import gc
                del sentence_model
                gc.collect()
                
        # 2. Advanced NLP & Impact Analysis
        impact_score = 0.0
        try:
            import spacy
            local_nlp = spacy.load("en_core_web_sm")
        except Exception:
            local_nlp = None

        if local_nlp:
            doc = local_nlp(applicant.iats_resume_text)
            
            # Elite Signal: Quantifiable impact (Action limits and numbers)
            valid_impacts = 0
            fluff_penalty = 0
            for sent in doc.sents:
                sent_text = sent.text.lower()
                has_metric = any(token.like_num or token.pos_ == 'NUM' for token in sent)
                has_action = any(token.lemma_ in ['lead', 'architect', 'manage', 'reduce', 'improve', 'increase', 'deliver', 'achieve'] for token in sent)
                
                if has_metric and has_action:
                    # Anti-Fluff logic: If they say "improved by 90%" but it has no technical context or Proper Nouns, it's fluff.
                    if self.anti_fluff_enabled:
                        has_tech = bool(re.search(r'(api|app|system|database|code|frontend|backend|sales|revenue|clients|users|queries|server|pipeline)', sent_text))
                        has_propn = any(t.pos_ == 'PROPN' for t in sent)
                        if has_tech or has_propn:
                            valid_impacts += 1
                        else:
                            fluff_penalty += 1
                    else:
                        valid_impacts += 1
            
            impact_score = min(valid_impacts * 25.0, 100.0) # 4 impacts = 100%
            if self.anti_fluff_enabled and fluff_penalty > 0:
                impact_score = max(0.0, impact_score - (fluff_penalty * 10))
            
            tokens = [token.lemma_.lower() for token in doc if not token.is_stop]
            processed_text = " ".join(tokens) + " " + resume_text
        else:
            processed_text = resume_text
            
        keyword_map = self._collect_keywords()
        for keyword in keyword_map:
            if not keyword: continue
            if all(part.lower() in processed_text for part in keyword.split()):
                matched_keywords.append(keyword)
                
        matched_weight = sum(keyword_map[keyword] for keyword in matched_keywords)
        total_keyword_weight = sum(keyword_map.values()) or 1.0
        legacy_keyword_score = (matched_weight / total_keyword_weight) * 100.0
        
        # Blended Keyword / Semantic / Impact Score for "keyword_score" field backward compatibility
        if sentence_model and local_nlp:
            if self.seniority_level == 'intern':
                sim_w, imp_w, leg_w = 0.8, 0.0, 0.2
            elif self.seniority_level == 'junior':
                sim_w, imp_w, leg_w = 0.65, 0.15, 0.2
            elif self.seniority_level == 'senior':
                sim_w, imp_w, leg_w = 0.3, 0.6, 0.1
            else: # mid
                sim_w, imp_w, leg_w = 0.4, 0.4, 0.2
            
            keyword_score = (semantic_sim * sim_w) + (impact_score * imp_w) + (legacy_keyword_score * leg_w)
            summary_details.append(f"Seniority Applied: {self.seniority_level.title()}")
            if self.anti_fluff_enabled and local_nlp and fluff_penalty > 0:
                summary_details.append(f"Anti-Fluff Penalty Applied: -{fluff_penalty * 10}% (Invalid Metrics)")
        else:
            keyword_score = legacy_keyword_score
            
        summary_details.append(f"Semantic Match: {semantic_sim:.1f}%")
        summary_details.append(f"Impact/Elite Factor: {impact_score:.1f}%")


        
        word_count = len(resume_text.split())
        if word_count < 80 or (word_count > 0 and len(matched_keywords) / word_count > 0.15):
            return {
                "total_score": 0.0,
                "keyword_score": 0.0,
                "skill_score": 0.0,
                "experience_score": 0.0,
                "education_score": 0.0,
                "completeness_score": 0.0,
                "years_experience": 0.0,
                "matched_keywords": "SUSPICIOUS FLAG",
                "recommendation": "reject",
                "summary": "WARNING: Keyword stuffing detected, or resume is too short. Automatic Reject."
            }

        skill_score = self._score_skills(applicant)

        years_experience = applicant.iats_years_experience or 0.0
        if years_experience <= 0.0:
            years_experience = self._extract_years_from_text(applicant.iats_resume_text)
        required_years = max(self.minimum_years_experience, 1.0)
        experience_score = min(years_experience / required_years, 1.0) * 100.0 if self.minimum_years_experience else 100.0

        education_score = self._score_education(applicant)
        completeness_score = self._score_completeness(applicant)

        total_score = (
            (keyword_score * normalized_weights["keyword"])
            + (skill_score * normalized_weights["skill"])
            + (experience_score * normalized_weights["experience"])
            + (education_score * normalized_weights["education"])
            + (completeness_score * normalized_weights["completeness"])
        ) / 100.0

        recommendation = self._build_recommendation(total_score)
        summary_lines = summary_details + [
            f"Legacy Keywords matched: {', '.join(matched_keywords[:10]) or 'None'}",
            f"Skills alignment: {skill_score:.1f}%",
            f"Experience detected: {years_experience:.1f} years",
            f"Education alignment: {education_score:.1f}%",
            f"Profile completeness: {completeness_score:.1f}%",
            f"Recommendation: {recommendation.title()}",
        ]
        return {
            "total_score": round(total_score, 2),
            "keyword_score": round(keyword_score, 2),
            "skill_score": round(skill_score, 2),
            "experience_score": round(experience_score, 2),
            "education_score": round(education_score, 2),
            "completeness_score": round(completeness_score, 2),
            "years_experience": round(years_experience, 2),
            "matched_keywords": ", ".join(matched_keywords[:20]),
            "recommendation": recommendation,
            "summary": "\n".join(summary_lines),
        }

    def _notify_reviewers(self, applicant):
        self.ensure_one()
        partner_ids = self.reviewer_user_ids.mapped("partner_id").ids
        if not partner_ids:
            return
        applicant.message_post(
            body=(
                f"IATS screened {applicant.partner_name or applicant.display_name} "
                f"for {self.job_id.name} with a score of {applicant.iats_score:.1f}."
            ),
            partner_ids=partner_ids,
            subtype_xmlid="mail.mt_note",
        )

    def action_screen_applicants(self):
        for profile in self:
            applicants = profile.applicant_ids.filtered(
                lambda applicant: applicant.iats_state in ('ready', 'pending') and applicant.iats_resume_parse_status == "ready" and applicant.active
            )
            for applicant in applicants:
                try:
                    applicant._run_iats_screening(profile=profile, force=False)
                    self.env.cr.commit()  # Auto-commit to prevent memory stack buildup on large batches
                except Exception as e:
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.error(f"Error screening applicant {applicant.id}: {str(e)}")
                    pass
        return True

    def action_view_ranked_applicants(self):
        self.ensure_one()
        return {
            "name": f"IATS Applicants - {self.job_id.name}",
            "type": "ir.actions.act_window",
            "res_model": "hr.applicant",
            "view_mode": "list,kanban,form",
            "domain": [("iats_profile_id", "=", self.id)],
            "context": {
                "search_default_iats_scored": 1,
                "default_job_id": self.job_id.id,
            },
        }

    @api.model
    def cron_screen_profiles(self):
        profiles = self.search([("active", "=", True), ("auto_screen_enabled", "=", True)])
        for profile in profiles:
            profile.action_screen_applicants()
