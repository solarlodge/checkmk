/**
 * Copyright (C) 2024 Checkmk GmbH - License: GNU General Public License v2
 * This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
 * conditions defined in the file COPYING, which is part of this source code package.
 */

import "nodevis/node_types";
import "nodevis/link_types";

import * as d3 from "d3";
import {
    FixLayer,
    layer_class_registry,
    LayerSelections,
    ToggleableLayer,
} from "nodevis/layer_utils";
import {
    AbstractLink,
    compute_link_id,
    link_type_class_registry,
} from "nodevis/link_utils";
import {AbstractGUINode, node_type_class_registry} from "nodevis/node_utils";
import * as texts from "nodevis/texts";
import {TranslationKey} from "nodevis/texts";
import {
    ContextMenuElement,
    Coords,
    d3SelectionDiv,
    d3SelectionG,
    NodevisLink,
    NodevisNode,
    NodevisWorld,
} from "nodevis/type_defs";
import {DefaultTransition} from "nodevis/utils";

export class ParentChildOverlay extends ToggleableLayer {
    override class_name(): string {
        return "parent_child";
    }

    override id(): string {
        return "parent_child";
    }

    override name() {
        return "Parent/Child";
    }

    override enable() {
        if (this.enabled) return;
        this.enabled = true;
        this._world.update_data();
    }
}

//#.
//#   .-Nodes Layer--------------------------------------------------------.
//#   |      _   _           _             _                               |
//#   |     | \ | | ___   __| | ___  ___  | |    __ _ _   _  ___ _ __      |
//#   |     |  \| |/ _ \ / _` |/ _ \/ __| | |   / _` | | | |/ _ \ '__|     |
//#   |     | |\  | (_) | (_| |  __/\__ \ | |__| (_| | |_| |  __/ |        |
//#   |     |_| \_|\___/ \__,_|\___||___/ |_____\__,_|\__, |\___|_|        |
//#   |                                               |___/                |
//#   +--------------------------------------------------------------------+

export class LayeredNodesLayer extends FixLayer {
    node_instances: Record<string, AbstractGUINode>;
    link_instances: Record<string, AbstractLink>;
    _links_for_node: Record<string, AbstractLink[]> = {};
    last_scale: number;

    nodes_selection: d3SelectionG;
    links_selection: d3SelectionG;
    popup_menu_selection: d3SelectionDiv;

    constructor(world: NodevisWorld, selections: LayerSelections) {
        super(world, selections);
        this.last_scale = 1;
        // Node instances by id
        this.node_instances = {};
        // NodeLink instances
        this.link_instances = {};

        // Nodes/Links drawn on screen
        this.links_selection = this._svg_selection
            .append("g")
            .attr("name", "viewport_layered_links")
            .attr("id", "links");
        this.nodes_selection = this._svg_selection
            .append("g")
            .attr("name", "viewport_layered_nodes")
            .attr("id", "nodes");
        this.popup_menu_selection = this._div_selection
            .append("div")
            .attr("id", "popup_menu")
            .style("pointer-events", "all")
            .style("position", "absolute")
            .classed("popup_menu", true)
            .style("display", "none");
    }

    override class_name(): string {
        return "nodes";
    }

    override id() {
        return "nodes";
    }

    get_node_by_id(node_id: string): AbstractGUINode {
        return this.node_instances[node_id];
    }

    get_links_for_node(node_id: string): AbstractLink[] {
        return this._links_for_node[node_id] || [];
    }

    simulation_end() {
        for (const name in this.node_instances) {
            this.node_instances[name].simulation_end_actions();
        }
    }

    override z_index(): number {
        return 50;
    }

    override name() {
        return "Nodes Layer";
    }

    override setup(): void {
        return;
    }

    override zoomed(): void {
        // Interrupt any gui transitions whenever the zoom factor is changed
        if (this.last_scale != this._world.viewport.last_zoom.k)
            this._svg_selection
                .selectAll(".node_element, .link_element")
                .interrupt();

        for (const idx in this.node_instances)
            this.node_instances[idx].update_quickinfo_position();

        if (this.last_scale != this._world.viewport.last_zoom.k)
            this.update_gui(true);

        this.last_scale = this._world.viewport.last_zoom.k;
    }

    override update_data(): void {
        this._update_nodes();
        this._update_links();
    }

    _update_nodes(): void {
        const visible_nodes = this._world.viewport
            .get_all_nodes()
            .filter(d => !d.data.invisible);

        const old_node_instances: Record<string, AbstractGUINode> =
            this.node_instances;
        this.node_instances = {};

        // Update data
        const node_ids: string[] = [];
        visible_nodes.forEach(node_config => {
            const new_node = this._create_node(node_config);
            this.node_instances[new_node.id()] = new_node;
            node_ids.push(new_node.id());
        });

        // Update GUI
        this.nodes_selection
            .selectAll<SVGGElement, string>(".node_element")
            .data(node_ids, d => {
                return d;
            })
            .join(
                enter => enter.append("g").classed("node_element", true),
                update => update,
                exit =>
                    exit.each((node_id, idx, node_list) => {
                        this._add_node_vanish_animation(
                            d3.select(node_list[idx]),
                            node_id,
                            old_node_instances
                        );
                    })
            )
            .each((node_id, idx, node_list) => {
                this.node_instances[node_id].render_into(
                    d3.select(node_list[idx])
                );
            });
    }

    _add_node_vanish_animation(
        node: d3.Selection<SVGGElement, unknown, null, undefined>,
        node_id: string,
        old_node_instances: Record<string, AbstractGUINode>
    ) {
        const old_instance = old_node_instances[node_id];
        if (!old_instance) {
            node.remove();
            return;
        }

        const vanish_coords = this._world.viewport.scale_to_zoom(
            this._world.viewport.compute_spawn_coords(old_instance.node)
        );

        // Move vanishing nodes, back to their parent nodes
        node.transition()
            .duration(DefaultTransition.duration())
            .attr(
                "transform",
                "translate(" + vanish_coords.x + "," + vanish_coords.y + ")"
            )
            .style("opacity", 0)
            .remove();
    }

    _update_links(): void {
        const link_configs = this._world.viewport.get_all_links();
        this._links_for_node = {};

        // Recreate instances
        this.link_instances = {};
        const link_ids: Set<string> = new Set();
        link_configs.forEach(link_config => {
            const link_id = compute_link_id(link_config);
            if (link_ids.has(link_id)) {
                return;
            }

            const new_link = this._create_link(link_config);
            this.link_instances[link_id] = new_link;
            link_ids.add(link_id);

            // Update quick references: {node_id : connected link[]}
            const source_id = link_config.source.data.id;
            const target_id = link_config.target.data.id;
            source_id in this._links_for_node ||
                (this._links_for_node[source_id] = []);
            target_id in this._links_for_node ||
                (this._links_for_node[target_id] = []);
            this._links_for_node[source_id].push(new_link);
            this._links_for_node[target_id].push(new_link);
        });

        // Update GUI
        this.links_selection
            .selectAll<SVGGElement, string>("g.link_element")
            .data(link_ids, d => d)
            .join("g")
            .classed("link_element", true)
            .each((link_id, idx, nodes) => {
                this.link_instances[link_id].render_into(d3.select(nodes[idx]));
            });
    }

    _create_node(node_data: NodevisNode): AbstractGUINode {
        const node_class = node_type_class_registry.get_class(
            node_data.data.node_type
        );
        return new node_class(this._world, node_data);
    }

    _create_link(link_data: NodevisLink): AbstractLink {
        let link_class = link_type_class_registry.get_class(
            link_data.config.type
        );
        // TODO: remove
        if (!link_class)
            link_class = link_type_class_registry.get_class("default");

        return new link_class(this._world, link_data);
    }

    override update_gui(force = false): void {
        this._update_position_of_context_menu();
        if (!force && this._world.viewport.get_force_alpha() < 0.11) {
            for (const idx in this.node_instances)
                this.node_instances[
                    idx
                ].node.data.transition_info.use_transition = false;
            return;
        }

        for (const idx in this.node_instances)
            this.node_instances[idx].update_position();

        for (const idx in this.link_instances) {
            this.link_instances[idx].update_position();
        }

        // Disable node transitions after each update step
        for (const idx in this.node_instances)
            this.node_instances[idx].node.data.transition_info.use_transition =
                false;
    }

    _add_toggle_options_to_context_menu(
        content_ul: d3.Selection<HTMLUListElement, null, any, unknown>
    ) {
        const nodes_class_list = this._svg_selection.node()!.classList;
        const hide_host_labels = nodes_class_list.contains("hide_host_labels");
        const hide_service_labels = nodes_class_list.contains(
            "hide_service_labels"
        );
        const hide_icons = nodes_class_list.contains("hide_icons");

        const data: [TranslationKey, boolean][] = [
            ["host_labels", !hide_host_labels],
            ["service_labels", !hide_service_labels],
            ["icons", !hide_icons],
        ];
        const elements: ContextMenuElement[] = [];
        data.forEach(([ident, is_active]) => {
            elements.push({
                text:
                    (is_active ? texts.get("hide") : texts.get("show")) +
                    " " +
                    texts.get(ident).toLowerCase(),
                on: (_event, d) => {
                    nodes_class_list.toggle("hide_" + d.data);
                },
                href: "",
                img: "themes/facelift/images/icon_aggr.svg",
                data: ident,
            });
        });

        this._add_elements_to_context_menu(content_ul, "visibility", elements);
    }
    override render_context_menu(
        event: MouseEvent,
        node_id: string | null
    ): void {
        event.preventDefault();
        event.stopPropagation();

        this.popup_menu_selection.selectAll("*").remove();
        const content_ul = this.popup_menu_selection.append("ul");
        this._add_toggle_options_to_context_menu(content_ul);

        let gui_node: AbstractGUINode | null = null;
        if (node_id)
            gui_node = this._world.viewport
                .get_nodes_layer()
                .get_node_by_id(node_id);

        // Create li for each item
        if (this._world.viewport.get_layout_manager().edit_layout) {
            // Add elements layout manager
            content_ul.append("li").append("hr");
            this._add_elements_to_context_menu(
                content_ul,
                "layouting",
                this._world.viewport
                    .get_layout_manager()
                    .get_context_menu_elements(gui_node ? gui_node.node : null)
            );
        }

        // Add elements from node
        if (gui_node) {
            content_ul.append("li").append("hr");
            this._add_elements_to_context_menu(
                content_ul,
                "node",
                gui_node.get_context_menu_elements()
            );
        } else {
            this.popup_menu_selection
                .style("left", event.offsetX + "px")
                .style("top", event.offsetY + "px");
        }

        this.popup_menu_selection.datum(gui_node);

        if (content_ul.selectAll("li").empty())
            this.popup_menu_selection.style("display", "none");
        else this._update_position_of_context_menu();
    }

    _add_elements_to_context_menu(
        content: d3.Selection<HTMLUListElement, null, any, unknown>,
        element_source: string,
        elements: ContextMenuElement[]
    ): void {
        // Renders links and html elements
        let links = content
            .selectAll<HTMLAnchorElement, ContextMenuElement>(
                "li" + "." + element_source + " a"
            )
            .data(elements.filter(element => !element.dom));

        links = links
            .join("li")
            .classed(element_source, true)
            .classed("popup_link", true)
            .append("a")
            .classed("noselect", true);

        // Add optional href
        links.each((d, idx, nodes) => {
            if (d.href) {
                d3.select(nodes[idx])
                    .attr("href", d.href)
                    .on("click", () => this.hide_context_menu());
            }
        });

        // Add optional img
        links.each(function (d) {
            if (d.img) {
                d3.select(this)
                    .append("img")
                    .classed("icon", true)
                    .attr("src", d.img);
            }
        });

        // Add text
        links.each(function (d) {
            if (d.text)
                d3.select(this)
                    .append("div")
                    .style("display", "inline-block")
                    .text(d.text);
        });

        // Add optional click handler
        links.each((d, idx, nodes) => {
            if (d.on) {
                d3.select(nodes[idx]).on("click", event => {
                    if (d.on) d.on(event, d);
                    this.hide_context_menu();
                });
            }
        });

        // @ts-ignore
        content
            .selectAll<HTMLDivElement, ContextMenuElement>(
                "li" + "." + element_source + " div.dom"
            )
            .data(elements.filter(element => element.dom))
            .enter()
            .append("li")
            .classed(element_source, true)
            .append("div")
            .classed("dom", true)
            .append(d => d.dom);
    }

    _update_position_of_context_menu(): void {
        if (this.popup_menu_selection.selectAll("li").empty()) return;

        this.popup_menu_selection.style("display", null);

        // Set position
        const gui_node =
            this.popup_menu_selection.datum() as AbstractGUINode | null;
        if (gui_node == null) return;

        const old_coords: Coords = {x: gui_node.node.x, y: gui_node.node.y};
        const new_coords = this._world.viewport.translate_to_zoom(old_coords);

        this.popup_menu_selection
            .style("left", new_coords.x + "px")
            .style("top", new_coords.y + "px");
    }

    override hide_context_menu(): void {
        this.popup_menu_selection.selectAll("*").remove();
        this.popup_menu_selection.style("display", "none");
    }
}

layer_class_registry.register(ParentChildOverlay);
layer_class_registry.register(LayeredNodesLayer);
