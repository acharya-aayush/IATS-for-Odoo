/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class IatsDashboardCard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            jobs: [],
            activeJobId: null,
            applicants: [],
            selectedAppIds: [],
            viewMode: 'list', // 'list' or 'compare'
        });

        onWillStart(async () => {
            await this.fetchJobs();
        });
    }

    async fetchJobs() {
        // Fetch all jobs to allow grouping
        const jobs = await this.orm.searchRead(
            'hr.job',
            [],
            ['id', 'name', 'no_of_recruitment'],
            { order: 'name asc' }
        );
        this.state.jobs = jobs;

        if (jobs.length > 0) {
            await this.selectJob(jobs[0].id);
        }
    }

    async selectJob(jobId) {
        this.state.activeJobId = jobId;
        this.state.selectedAppIds = [];
        this.state.viewMode = 'list';
        
        // Fetch only scored applicants for the selected job
        const applicants = await this.orm.searchRead(
            'hr.applicant',
            [['job_id', '=', jobId], ['iats_state', '=', 'scored']],
            [
                'id', 
                'partner_name', 
                'iats_score', 
                'iats_recommendation', 
                'iats_skill_score', 
                'iats_experience_score', 
                'iats_education_score', 
                'iats_keyword_score', 
                'iats_completeness_score', 
                'iats_match_summary',
                'iats_matched_skills',
                'iats_missing_skills',
                'iats_red_flags'
            ],
            { order: 'iats_score desc', limit: 50 }
        );
        this.state.applicants = applicants;
    }

    toggleSelection(appId) {
        if (this.state.selectedAppIds.includes(appId)) {
            this.state.selectedAppIds = this.state.selectedAppIds.filter(id => id !== appId);
        } else {
            if (this.state.selectedAppIds.length < 4) {
                this.state.selectedAppIds.push(appId);
            } else {
                alert("You can only compare up to 4 candidates at a time for optimal viewing.");
            }
        }
    }

    toggleCompareMode() {
        if (this.state.viewMode === 'list' && this.state.selectedAppIds.length >= 2) {
            this.state.viewMode = 'compare';
        } else {
            this.state.viewMode = 'list';
        }
    }

    get selectedApplicantsData() {
        return this.state.applicants.filter(a => this.state.selectedAppIds.includes(a.id));
    }

    openApplicant(applicantId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'hr.applicant',
            res_id: applicantId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    getScoreColor(score) {
        if (score >= 80) return 'bg-success';
        if (score >= 60) return 'bg-warning';
        return 'bg-danger';
    }
}

IatsDashboardCard.template = "iats_recruitment.DashboardCard";
registry.category("actions").add("iats.commands_dashboard", IatsDashboardCard);
