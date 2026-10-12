import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

const LEVELS = [
    { label: _t("Enter a new password") },
    { label: _t("Weak"), cls: "o_rp_pw_weak" },
    { label: _t("Fair"), cls: "o_rp_pw_fair" },
    { label: _t("Good"), cls: "o_rp_pw_good" },
    { label: _t("Strong"), cls: "o_rp_pw_strong" },
];

/**
 * Change password form of the tenant security page: strength hint on the new password and
 * live check that the confirmation matches. Only a hint: the server applies the real rules.
 */
export class RentPasswordStrength extends Interaction {
    static selector = ".o_rp_password_form";
    dynamicContent = {
        "input[name='new1']": { "t-on-input": this.update },
        "input[name='new2']": { "t-on-input": this.update },
        ".o_rp_pw_strength": {
            "t-att-class": () =>
                Object.fromEntries(LEVELS.slice(1).map((level, i) => [level.cls, this.level === i + 1])),
        },
        ".o_rp_pw_strength_label": { "t-out": () => LEVELS[this.level].label },
        ".o_rp_pw_match": {
            "t-out": () => this.matchText,
            "t-att-class": () => ({ o_rp_pw_ok: this.match === true, o_rp_pw_ko: this.match === false }),
        },
    };

    setup() {
        this.new1 = this.el.querySelector("input[name='new1']");
        this.new2 = this.el.querySelector("input[name='new2']");
        this.level = 0;
        this.match = null;
        this.matchText = "";
    }

    update() {
        const value = this.new1.value;
        let score = 0;
        if (value) {
            score = 1;
            if (value.length >= 8) {
                score++;
            }
            const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((re) => re.test(value)).length;
            if (kinds >= 3) {
                score++;
            }
            if (value.length >= 12 && kinds >= 3) {
                score++;
            }
        }
        this.level = score;
        if (!this.new2.value) {
            this.match = null;
            this.matchText = "";
        } else {
            this.match = this.new2.value === value;
            this.matchText = this.match ? _t("Passwords match") : _t("Passwords don't match yet");
        }
    }
}

registry
    .category("public.interactions")
    .add("rent_management.password_strength", RentPasswordStrength);
