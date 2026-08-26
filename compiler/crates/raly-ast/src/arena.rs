//! A typed index arena, and the string interner.
//!
//! Nodes live in flat `Vec`s and refer to each other by 32-bit index rather
//! than by `Box`. That is not a micro-optimisation: it makes every node
//! `Copy`-cheap to reference, makes the whole tree trivially serialisable,
//! lets later phases hang side tables (types, resolutions, spans) off the same
//! indices without touching the tree, and sidesteps the lifetime problems that
//! make `&'ast Node` trees painful to build incrementally during error
//! recovery.

use std::fmt;
use std::hash::{Hash, Hasher};
use std::marker::PhantomData;

/// A handle to a `T` stored in an [`Arena<T>`].
pub struct Id<T> {
    raw: u32,
    _marker: PhantomData<fn() -> T>,
}

impl<T> Id<T> {
    pub fn index(self) -> usize {
        self.raw as usize
    }

    /// Only for serialisation and debugging; prefer passing `Id` around.
    pub fn from_raw(raw: u32) -> Self {
        Id {
            raw,
            _marker: PhantomData,
        }
    }

    pub fn raw(self) -> u32 {
        self.raw
    }
}

// Derived impls would demand `T: Clone` and friends, which is wrong: an `Id`
// is just a number and never owns a `T`.
impl<T> Clone for Id<T> {
    fn clone(&self) -> Self {
        *self
    }
}
impl<T> Copy for Id<T> {}
impl<T> PartialEq for Id<T> {
    fn eq(&self, other: &Self) -> bool {
        self.raw == other.raw
    }
}
impl<T> Eq for Id<T> {}
impl<T> Hash for Id<T> {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.raw.hash(state);
    }
}
impl<T> fmt::Debug for Id<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "#{}", self.raw)
    }
}

/// A flat, append-only store of `T`.
#[derive(Debug)]
pub struct Arena<T> {
    items: Vec<T>,
}

impl<T> Default for Arena<T> {
    fn default() -> Self {
        Arena { items: Vec::new() }
    }
}

impl<T> Arena<T> {
    pub fn new() -> Self {
        Arena::default()
    }

    pub fn alloc(&mut self, value: T) -> Id<T> {
        let id = Id::from_raw(self.items.len() as u32);
        self.items.push(value);
        id
    }

    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn is_empty(&self) -> bool {
        self.items.is_empty()
    }

    pub fn get(&self, id: Id<T>) -> Option<&T> {
        self.items.get(id.index())
    }

    pub fn get_mut(&mut self, id: Id<T>) -> Option<&mut T> {
        self.items.get_mut(id.index())
    }

    /// Every id in allocation order.
    pub fn ids(&self) -> impl Iterator<Item = Id<T>> + use<T> {
        (0..self.items.len() as u32).map(Id::from_raw)
    }

    pub fn iter(&self) -> std::slice::Iter<'_, T> {
        self.items.iter()
    }
}

impl<T> std::ops::Index<Id<T>> for Arena<T> {
    type Output = T;
    fn index(&self, id: Id<T>) -> &T {
        &self.items[id.index()]
    }
}

impl<T> std::ops::IndexMut<Id<T>> for Arena<T> {
    fn index_mut(&mut self, id: Id<T>) -> &mut T {
        &mut self.items[id.index()]
    }
}

/// An interned identifier or string. Comparing two `Symbol`s is an integer
/// compare, which is what makes name resolution cheap later.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Symbol(u32);

impl Symbol {
    /// The interner index behind this symbol.
    ///
    /// Only for hashing and serialisation; comparing `Symbol`s directly is
    /// what the type is for.
    pub fn as_u32(self) -> u32 {
        self.0
    }
}

impl fmt::Debug for Symbol {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "sym#{}", self.0)
    }
}

/// Deduplicating string store. Lives on the [`crate::Ast`].
#[derive(Debug, Default)]
pub struct Interner {
    lookup: std::collections::HashMap<String, Symbol>,
    strings: Vec<String>,
}

impl Interner {
    pub fn new() -> Self {
        Interner::default()
    }

    pub fn intern(&mut self, text: &str) -> Symbol {
        if let Some(&sym) = self.lookup.get(text) {
            return sym;
        }
        let sym = Symbol(self.strings.len() as u32);
        self.strings.push(text.to_owned());
        self.lookup.insert(text.to_owned(), sym);
        sym
    }

    pub fn resolve(&self, sym: Symbol) -> &str {
        &self.strings[sym.0 as usize]
    }

    pub fn len(&self) -> usize {
        self.strings.len()
    }

    pub fn is_empty(&self) -> bool {
        self.strings.is_empty()
    }
}
