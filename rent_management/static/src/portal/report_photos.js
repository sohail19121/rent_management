import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

const MAX_PHOTOS = 5;

/**
 * Photo drop zone of the "Report a problem" page: drag & drop, previews, remove before sending.
 * The files stay in the form's file input, so the form posts them as usual.
 */
export class RentReportPhotos extends Interaction {
    static selector = ".o_rp_report_form";
    dynamicContent = {
        ".o_rp_dropzone": {
            "t-on-dragover.prevent": () => this.setDragging(true),
            "t-on-dragleave": () => this.setDragging(false),
            "t-on-drop.prevent": this.onDrop,
            "t-att-class": () => ({ o_rp_dragging: this.dragging }),
        },
        "#o_rp_photos": { "t-on-change": this.renderPreviews },
    };

    setup() {
        this.dragging = false;
        this.input = this.el.querySelector("#o_rp_photos");
        this.previews = this.el.querySelector(".o_rp_previews");
    }

    setDragging(value) {
        this.dragging = value;
    }

    onDrop(ev) {
        this.dragging = false;
        this.setFiles([...this.input.files, ...ev.dataTransfer.files]);
    }

    setFiles(files) {
        const transfer = new DataTransfer();
        files.filter((file) => file.type.startsWith("image/"))
            .slice(0, MAX_PHOTOS)
            .forEach((file) => transfer.items.add(file));
        this.input.files = transfer.files;
        this.renderPreviews();
    }

    renderPreviews() {
        if (this.input.files.length > MAX_PHOTOS) {
            this.setFiles([...this.input.files]);
            return;
        }
        this.previews.replaceChildren();
        [...this.input.files].forEach((file, index) => {
            const item = document.createElement("div");
            item.className = "o_rp_preview";
            const img = document.createElement("img");
            img.alt = file.name;
            img.src = URL.createObjectURL(file);
            img.onload = () => URL.revokeObjectURL(img.src);
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "o_rp_preview_remove";
            remove.setAttribute("aria-label", `Remove ${file.name}`);
            remove.innerHTML = '<i class="oi" data-icon="close"></i>';
            remove.addEventListener("click", () =>
                this.setFiles([...this.input.files].filter((_, i) => i !== index))
            );
            item.append(img, remove);
            this.previews.append(item);
        });
    }
}

registry.category("public.interactions").add("rent_management.report_photos", RentReportPhotos);
