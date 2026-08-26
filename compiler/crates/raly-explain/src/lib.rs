//! `raly explain` — a Raly program, in plain English, derived entirely from
//! its types.
//!
//! This is the feature that demonstrates the project's thesis. Every other
//! language can print a program's signatures; none of them can say what the
//! program *means*, because none of their types carry meaning. A Rust
//! signature says `Vec<f32> -> Vec<f32>`. A Raly signature says: three atoms
//! of a 384-wide MAP space go in, and what comes back carries the roles
//! `Subject`, `Verb` and `Object`, holds three of the three items measurement
//! says that space can retrieve, and is therefore exactly at capacity.
//!
//! Three rules govern everything below, and they are the deliverable:
//!
//! 1. **Plain words.** No term is used that is not defined where it is used.
//!    A reader who does not know what a vector space is should still learn
//!    something true.
//! 2. **Only what the types prove.** Where a property is open or unknown, the
//!    output says so. It never fills a gap with the likely answer.
//! 3. **Say the unwritten.** A vector at or near capacity, a role schema left
//!    open, a value that is an approximate inverse, a nesting depth that will
//!    need a cleanup — all of these follow from the types without appearing in
//!    the source, and all of them are flagged.
//!
//! ```ignore
//! let compiled = raly::compile("scene.raly", source);
//! let explained = raly_explain::explain(&compiled.ast, &compiled.resolved, &compiled.checked, "scene.raly");
//! print!("{}", raly_explain::render::plain(&explained));
//! ```

#![deny(missing_debug_implementations)]

pub mod model;
pub mod render;
pub mod words;

pub use model::{Described, Explanation, Fact};

use raly_ast::{Ast, ExprKind, ItemId, ItemKind};
use raly_resolve::Resolved;
use raly_types::{CapacityBasis, Checked, Load, Names, SpaceId, SpaceInfo, Ty, VecTy};

/// Explain one checked file.
///
/// Pure, like every other phase, and total: a file that does not type-check
/// still gets explained as far as its types are known, because a reader asking
/// "what is this program?" is often asking precisely because it does not work
/// yet.
pub fn explain(ast: &Ast, resolved: &Resolved, checked: &Checked, file: &str) -> Explanation {
    Explainer {
        ast,
        resolved,
        checked,
    }
    .run(file)
}

#[derive(Debug)]
struct Explainer<'a> {
    ast: &'a Ast,
    resolved: &'a Resolved,
    checked: &'a Checked,
}

impl Explainer<'_> {
    fn names(&self) -> Names<'_> {
        Names {
            spaces: &self.checked.spaces,
            defs: &self.resolved.defs,
        }
    }

    fn show(&self, ty: &Ty) -> String {
        self.names().show(ty)
    }

    fn space_info(&self, id: SpaceId) -> Option<&SpaceInfo> {
        self.checked.spaces.get(id.index())
    }

    fn run(&self, file: &str) -> Explanation {
        let mut items = Vec::new();
        let mut counts = [0usize; 4];
        for &item in &self.ast.root {
            let described = match &self.ast.items[item].kind {
                ItemKind::Space(_) => {
                    counts[0] += 1;
                    self.describe_space(item)
                }
                ItemKind::Role(_) => {
                    counts[1] += 1;
                    self.describe_role(item)
                }
                ItemKind::TypeAlias(_) => {
                    counts[2] += 1;
                    self.describe_alias(item)
                }
                ItemKind::Fn(_) => {
                    counts[3] += 1;
                    self.describe_fn(item)
                }
                _ => None,
            };
            items.extend(described);
        }
        Explanation {
            file: file.to_string(),
            headline: headline(counts),
            items,
        }
    }

    // -- spaces --------------------------------------------------------------

    fn describe_space(&self, item: ItemId) -> Option<Described> {
        let ItemKind::Space(decl) = &self.ast.items[item].kind else {
            return None;
        };
        let name = self.ast.text(decl.name).to_string();
        let def = self.resolved.def_of_item(item)?;
        let id = self
            .checked
            .spaces
            .iter()
            .position(|s| s.def == def)
            .map(|i| SpaceId(i as u32))?;
        let info = self.space_info(id)?;

        let mut out = Described::new("space", &name);
        let family = info.family.map(|f| f.name()).unwrap_or("?");
        // A width the checker could not work out is *not* reported. `dim`
        // falls back to the identity so that comparisons still work, and
        // printing that placeholder as the space's width would be the one
        // thing this whole feature promises never to do.
        let width = if info.dim_known {
            info.dim.to_string()
        } else {
            "?".to_string()
        };
        out.signature = format!("space {name} = {family}[{width}]");

        match (info.family, info.dim_known) {
            (Some(f), true) => out.say(format!(
                "A value of `{name}` is a list of {width} numbers, where {}. Nothing about that \
                 list means anything on its own; its meaning is which other values it was built \
                 from.",
                words::family(f)
            )),
            (Some(f), false) => out.say(format!(
                "A value of `{name}` is a list of numbers, where {}. How long that list is, the \
                 declaration does not say in a way the compiler can evaluate, so its width is \
                 unknown here.",
                words::family(f)
            )),
            (None, _) => out.say(format!(
                "`{name}` does not name a family the compiler knows, so what its numbers are, \
                 and how two of them combine, is unknown here."
            )),
        }

        out.say(
            "Several values can be added together into a single one, which is what `load` \
             counts everywhere below. That only works up to a point. Past it, asking for one of \
             the items back returns a different item instead, and nothing fails while it \
             happens."
                .to_string(),
        );

        match (info.capacity, info.capacity_dim) {
            (Some(capacity), Some(dimension)) => {
                let measured = match info.capacity_basis {
                    CapacityBasis::Effective => format!(
                        " That number comes from the measured effective width of {dimension} \
                         this declaration records, not from the {} written beside the family: \
                         a real embedding space uses far fewer independent directions than its \
                         nominal width suggests.",
                        info.dim
                    ),
                    CapacityBasis::Nominal => String::new(),
                };
                out.say(format!(
                    "For `{name}` that point is {capacity} items. It was measured at 95% \
                     retrieval, not derived from a formula.{measured}"
                ));
            }
            _ => out.say(format!(
                "How many items one `{name}` value can hold is unknown, because its width is \
                 not a compile-time constant and capacity is worked out from the width."
            )),
        }

        if info.capacity_basis == CapacityBasis::Effective {
            if let (Some(effective), Some(nominal)) = (info.capacity, self.nominal_capacity(info)) {
                if nominal > effective {
                    out.flag(format!(
                        "The written width would suggest room for {nominal} items. The measured \
                         width says {effective}. Anything sized against the written number is \
                         about {}x too optimistic.",
                        nominal / effective.max(1)
                    ));
                }
            }
        }

        let attrs: Vec<String> = decl
            .attrs
            .iter()
            .map(|a| self.ast.text(a.name).to_string())
            .collect();
        if !attrs.is_empty() {
            out.say(format!(
                "The declaration also records {}.",
                words::and_list(&attrs)
            ));
        }

        out.fact(
            "family",
            info.family
                .map(|f| Fact::text(f.name()))
                .unwrap_or(Fact::Unknown),
        );
        out.fact(
            "dimension",
            Fact::maybe_number(info.dim.as_constant().filter(|_| info.dim_known)),
        );
        out.fact("capacity_dimension", Fact::maybe_number(info.capacity_dim));
        out.fact(
            "capacity_basis",
            Fact::text(match info.capacity_basis {
                CapacityBasis::Effective => "measured effective width",
                CapacityBasis::Nominal => "declared width",
            }),
        );
        out.fact("capacity", Fact::maybe_number(info.capacity.map(u64::from)));
        out.fact("attributes", Fact::List(attrs));
        Some(out)
    }

    /// What capacity the *written* width would have promised, so the explainer
    /// can say how far off it is.
    fn nominal_capacity(&self, info: &SpaceInfo) -> Option<u32> {
        info.dim
            .as_constant()
            .filter(|_| info.dim_known)
            .map(raly_types::ty::capacity_of)
    }

    // -- roles ---------------------------------------------------------------

    fn describe_role(&self, item: ItemId) -> Option<Described> {
        let ItemKind::Role(decl) = &self.ast.items[item].kind else {
            return None;
        };
        let names: Vec<String> = decl
            .names
            .iter()
            .map(|n| self.ast.text(*n).to_string())
            .collect();
        if names.is_empty() {
            return None;
        }
        let space = decl.space.map(|s| self.ast.text(s).to_string());
        let mut out = Described::new("role", names.join(", "));
        out.signature = match &space {
            Some(space) => format!("role {} in {space}", names.join(", ")),
            None => format!("role {}", names.join(", ")),
        };
        match &space {
            Some(space) => out.say(format!(
                "{} {} fixed {} of `{space}`, used as {}: attaching a value to {} is how this \
                 program records which part that value plays.",
                words::and_list(&names),
                if names.len() == 1 { "is a" } else { "are" },
                if names.len() == 1 { "value" } else { "values" },
                if names.len() == 1 { "a key" } else { "keys" },
                if names.len() == 1 {
                    "it"
                } else {
                    "one of them"
                },
            )),
            None => out.say(format!(
                "{} are used as keys, but which space they come from is unknown, so the \
                 compiler cannot tell whether a value attached to one belongs with the rest.",
                words::and_list(&names)
            )),
        }
        out.say(
            "Which keys a value carries is a compile-time fact, tracked through every \
             operation, even though the values attached to them are not."
                .to_string(),
        );
        out.fact("names", Fact::List(names));
        out.fact("space", space.map(Fact::Text).unwrap_or(Fact::Unknown));
        Some(out)
    }

    // -- type aliases --------------------------------------------------------

    fn describe_alias(&self, item: ItemId) -> Option<Described> {
        let ItemKind::TypeAlias(alias) = &self.ast.items[item].kind else {
            return None;
        };
        let name = self.ast.text(alias.name).to_string();
        let ty = self.checked.type_of_item(item)?;
        let mut out = Described::new("type", &name);
        out.signature = format!("type {name} = {}", self.show(ty));
        out.say(format!("`{name}` is a name for {}.", self.describe_ty(ty)));
        for flag in self.notables(ty) {
            out.flag(flag);
        }
        out.fact("type", Fact::text(self.show(ty)));
        self.vector_facts(ty, &mut out);
        Some(out)
    }

    // -- functions -----------------------------------------------------------

    fn describe_fn(&self, item: ItemId) -> Option<Described> {
        let ItemKind::Fn(def) = &self.ast.items[item].kind else {
            return None;
        };
        let name = self.ast.text(def.name).to_string();
        let Some(Ty::Fn { params, ret }) = self.checked.type_of_item(item) else {
            return None;
        };
        let param_names: Vec<String> = def
            .params
            .iter()
            .map(|p| self.ast.text(p.name).to_string())
            .collect();

        let mut out = Described::new("fn", &name);
        let written: Vec<String> = param_names
            .iter()
            .zip(params)
            .map(|(n, t)| format!("{n}: {}", self.show(t)))
            .collect();
        out.signature = format!("fn {name}({}) -> {}", written.join(", "), self.show(ret));

        if params.is_empty() {
            out.say("It takes nothing.".to_string());
        } else if params.len() > 1 && params.iter().all(|p| p == &params[0]) {
            out.say(format!(
                "It takes {} values, every one of them {}.",
                words::count(params.len()),
                self.describe_ty(&params[0])
            ));
        } else {
            for (label, ty) in param_names.iter().zip(params) {
                out.say(format!("`{label}` is {}.", self.describe_ty(ty)));
            }
        }
        out.say(format!("It gives back {}.", self.describe_ty(ret)));

        // The declared result and the type the body actually has can differ in
        // ways an annotation cannot express — how noisy a value is, and how
        // many unbinds deep it sits — so the body is consulted where it knows
        // more than the signature does.
        let body_ty = self.body_type(item);
        let observed = body_ty.as_ref().unwrap_or(ret);
        for flag in self.notables(observed) {
            out.flag(flag);
        }

        out.fact("parameters", Fact::List(written));
        out.fact("result", Fact::text(self.show(ret)));
        if let Some(body) = &body_ty {
            out.fact("result_of_the_body", Fact::text(self.show(body)));
        }
        self.vector_facts(observed, &mut out);
        Some(out)
    }

    /// The type of a function body's tail expression, when there is one.
    fn body_type(&self, item: ItemId) -> Option<Ty> {
        let ItemKind::Fn(def) = &self.ast.items[item].kind else {
            return None;
        };
        let body = def.body?;
        let tail = match &self.ast.exprs[body].kind {
            ExprKind::Block { tail, .. } => (*tail)?,
            _ => body,
        };
        self.checked.type_of(tail).cloned()
    }

    // -- types, in words -----------------------------------------------------

    fn describe_ty(&self, ty: &Ty) -> String {
        match ty {
            Ty::Error => "something the compiler could not work out".to_string(),
            Ty::Unit => "nothing".to_string(),
            Ty::Int => "a whole number".to_string(),
            Ty::Float => "a number with a fractional part".to_string(),
            Ty::Bool => "either true or false".to_string(),
            Ty::Str => "a piece of text".to_string(),
            Ty::Space(id) => format!("the space `{}` itself", self.names().space(*id)),
            Ty::Sym { space, .. } => match space {
                Some(id) => format!(
                    "one single entry of `{}` — one of its fixed values, not a combination of \
                     several",
                    self.names().space(*id)
                ),
                None => "one single entry of a space the compiler could not work out".to_string(),
            },
            Ty::Vec(v) => self.describe_vec(v),
            Ty::Fn { params, ret } => format!(
                "a function taking {} and giving back {}",
                if params.is_empty() {
                    "nothing".to_string()
                } else {
                    words::and_list(
                        &params
                            .iter()
                            .map(|p| self.describe_ty(p))
                            .collect::<Vec<_>>(),
                    )
                },
                self.describe_ty(ret)
            ),
            Ty::Tuple(elems) => format!(
                "{} values side by side: {}",
                words::count(elems.len()),
                words::and_list(
                    &elems
                        .iter()
                        .map(|e| self.describe_ty(e))
                        .collect::<Vec<_>>()
                )
            ),
            Ty::List(elem) => format!(
                "a list, kept side by side rather than added together, of {}",
                self.describe_ty(elem)
            ),
        }
    }

    fn describe_vec(&self, v: &VecTy) -> String {
        let space = v.space.and_then(|id| self.space_info(id));
        let mut text = match v.space {
            Some(id) => format!("a value of `{}`", self.names().space(id)),
            None => "a value of a space the compiler could not work out".to_string(),
        };

        let roles = self.role_names(v);
        match (roles.is_empty(), v.roles.open) {
            (false, false) => text.push_str(&format!(
                " carrying exactly the keys {}",
                words::and_list(&roles)
            )),
            (false, true) => text.push_str(&format!(
                " carrying at least the keys {}",
                words::and_list(&roles)
            )),
            (true, false) => text.push_str(" carrying no keys at all"),
            (true, true) => text.push_str(" whose keys the type does not pin down"),
        }

        text.push_str(&format!(
            ", holding {}",
            words::load_against_capacity(v.load, space)
        ));

        match v.clean {
            Some(true) => text.push_str(", and known to be one of the space's own entries"),
            Some(false) => text.push_str(", and not yet matched back to one of them"),
            None => {}
        }
        text
    }

    fn role_names(&self, v: &VecTy) -> Vec<String> {
        let mut names = Vec::new();
        for (label, count) in v.roles.labels() {
            for _ in 0..count {
                names.push(self.resolved.def(label).name.clone());
            }
        }
        names
    }

    // -- what the types say that the source does not -------------------------

    /// The flags the feature exists for: at or near capacity, an open role
    /// schema, an approximate inverse, and a nesting depth that will need a
    /// cleanup. None of these is written anywhere in the source.
    fn notables(&self, ty: &Ty) -> Vec<String> {
        let Some(v) = ty.as_vector() else {
            return Vec::new();
        };
        let mut out = Vec::new();
        if let Some((space, capacity)) = self
            .space_of(&v)
            .and_then(|s| s.capacity.map(|c| (s, c)))
            .filter(|_| v.load.is_exact())
        {
            let held = v.load.minimum();
            if held == capacity {
                out.push(format!(
                    "This is exactly at capacity: {held} of the {capacity} items `{}` can hold. \
                     One more and asking for an item back starts returning a different one, with \
                     nothing failing to say so.",
                    space.name
                ));
            } else if held > capacity {
                out.push(format!(
                    "This is past capacity: {} in a space that holds {capacity}. Some of what \
                     goes in cannot be got back out.",
                    words::items(held)
                ));
            } else if u64::from(held) * 10 >= u64::from(capacity) * 8 {
                out.push(format!(
                    "This is close to capacity: {held} of the {capacity} items `{}` can hold, \
                     leaving room for {} more.",
                    space.name,
                    capacity - held
                ));
            }
        }
        if v.roles.open {
            out.push(
                "The set of keys is left open, so the compiler knows some of what this carries \
                 but cannot prove any particular key is absent. Asking for a key that was never \
                 attached returns noise, and nothing here can catch that."
                    .to_string(),
            );
        }
        if v.clean == Some(false) {
            out.push(
                "Getting a value back out is only approximate: it returns what was asked for \
                 plus a little of everything else that was combined with it. Matching it \
                 against the space's own entries with `cleanup` is what makes it exact again, \
                 and that has not happened here."
                    .to_string(),
            );
        }
        if v.depth >= 2 {
            out.push(format!(
                "This is {} levels of extraction deep with nothing matched back in between. \
                 Measurement puts the usable depth at about two, so a `cleanup` belongs between \
                 the levels.",
                v.depth
            ));
        }
        out
    }

    fn space_of(&self, v: &VecTy) -> Option<&SpaceInfo> {
        v.space.and_then(|id| self.space_info(id))
    }

    /// The numbers behind the prose, for `--json`.
    fn vector_facts(&self, ty: &Ty, out: &mut Described) {
        let Some(v) = ty.as_vector() else { return };
        out.fact(
            "space",
            v.space
                .map(|id| Fact::text(self.names().space(id)))
                .unwrap_or(Fact::Unknown),
        );
        out.fact("load_low", Fact::Number(u64::from(v.load.minimum())));
        out.fact(
            "load_high",
            if v.load.high == Load::UNBOUNDED {
                Fact::Unknown
            } else {
                Fact::Number(u64::from(v.load.high))
            },
        );
        out.fact(
            "capacity",
            Fact::maybe_number(self.space_of(&v).and_then(|s| s.capacity).map(u64::from)),
        );
        out.fact("roles", Fact::List(self.role_names(&v)));
        out.fact("role_schema_open", Fact::Bool(v.roles.open));
        out.fact(
            "matched_to_a_codebook_entry",
            match v.clean {
                Some(clean) => Fact::Bool(clean),
                None => Fact::Unknown,
            },
        );
        out.fact("unbind_depth", Fact::Number(u64::from(v.depth)));
    }
}

fn headline(counts: [usize; 4]) -> String {
    let labels = [
        ("space", "spaces"),
        ("role declaration", "role declarations"),
        ("named type", "named types"),
        ("function", "functions"),
    ];
    let parts: Vec<String> = counts
        .iter()
        .zip(labels)
        .filter(|(n, _)| **n > 0)
        .map(|(n, (one, many))| format!("{n} {}", if *n == 1 { one } else { many }))
        .collect();
    if parts.is_empty() {
        return "This file declares nothing the compiler can describe.".to_string();
    }
    format!("This file declares {}.", words::and_list(&parts))
}
