import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

/** Copy buttons of the tenant pages: `data-rp-copy` holds the selector of the text to copy. */
export class RentCopyText extends Interaction {
    static selector = "[data-rp-copy]";
    dynamicContent = {
        _root: {
            "t-on-click": this.copy,
            "t-att-class": () => ({ o_rp_copied: this.copied }),
        },
    };

    setup() {
        this.copied = false;
    }

    async copy() {
        const target = document.querySelector(this.el.dataset.rpCopy);
        if (!target) {
            return;
        }
        await this.waitFor(navigator.clipboard.writeText(target.textContent.trim()));
        this.copied = true;
        this.services.notification.add(_t("Copied to clipboard"), { type: "success" });
        this.waitForTimeout(() => (this.copied = false), 2000);
    }
}

registry.category("public.interactions").add("rent_management.copy_text", RentCopyText);
