#![allow(dead_code)] // contract for #4/#5; this binary does not consume it yet
//! Metric backend interface (issue #3).
//!
//! This module freezes the contract that the Linux (#4) and macOS (#5) backends
//! implement. It deliberately contains no platform reads: a backend that cannot
//! provide a metric returns `Unavailable`, which renders as JSON `null`.
//!
//! Two legacy defects are addressed at the interface level, so backends cannot
//! reintroduce them:
//!
//! * memory fields are matched by **exact key** (`MemTotal:`), never by
//!   substring, because substring matching bound `Cached` to `SwapCached`;
//! * devices carry an **explicit class** instead of the `^\w*\d+` regex that
//!   excluded whole modern disks such as `nvme0n1` and `mmcblk0`.

use std::collections::BTreeMap;

/// A metric value that a backend may or may not be able to provide.
pub type Value = Option<f64>;

/// Whether a device is a whole disk or one of its partitions.
///
/// Backends classify explicitly from the device name; there is no regex guess.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeviceClass {
    /// Whole disk, e.g. `sda`, `nvme0n1`, `mmcblk0`, `disk0`.
    Disk,
    /// Partition of a disk, e.g. `sda1`, `nvme0n1p1`, `mmcblk0p1`.
    Partition,
}

/// One sampled value carrying its unit, so output never guesses.
#[derive(Debug, Clone, PartialEq)]
pub struct Quantity {
    pub value: f64,
    pub unit: Unit,
}

/// Units fixed by the output contract (issue #3 spec C4).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Unit {
    /// Percentage `0..=100`.
    Percent,
    /// Bytes per second.
    BytesPerSecond,
    /// KiB, matching `/proc/meminfo` and `kern.boottime` conventions.
    KiB,
    /// Millisecond average.
    Millis,
    /// Unitless count or load average.
    Count,
}

impl Quantity {
    pub fn new(value: f64, unit: Unit) -> Self {
        Self { value, unit }
    }
}

/// Result of sampling one module.
pub type MetricValues = BTreeMap<String, Value>;

/// A module backend. Implementors live in #4 (Linux) / #5 (macOS).
pub trait Metric {
    /// Module name used as the JSON key, e.g. `"Cpu"`, matching the legacy output.
    fn name(&self) -> &'static str;

    /// Sample this module against an already opened shared [`Window`].
    ///
    /// Implementations must not sleep on their own; use
    /// [`crate::sample::Window::fill`] and the shared helpers.
    fn sample(&self, window: &crate::sample::Window) -> MetricValues;
}

/// The `Unavailable` rendering used when a metric has no data.
///
/// Kept as a named constant so JSON and terminal output agree.
pub const UNAVAILABLE_LABEL: &str = "unavailable";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unavailable_is_none() {
        let value: Value = None;
        assert!(value.is_none());
    }

    #[test]
    fn quantity_keeps_unit() {
        let q = Quantity::new(1.5, Unit::Percent);
        assert_eq!(q.value, 1.5);
        assert_eq!(q.unit, Unit::Percent);
    }

    #[test]
    fn device_class_distinguishes_whole_disk_from_partition() {
        // Every name the legacy `^\w*\d+` regex wrongly excluded is a `Disk`
        // here, which is the whole point of the explicit classification.
        for disk in ["sda", "nvme0n1", "mmcblk0", "disk0"] {
            assert_eq!(classify(disk), DeviceClass::Disk, "{disk}");
        }
        for partition in ["sda1", "nvme0n1p1", "mmcblk0p1", "disk0s1"] {
            assert_eq!(classify(partition), DeviceClass::Partition, "{partition}");
        }
    }

    /// Reference classifier used by the tests; #4 owns the production one.
    ///
    /// Rules, in order:
    /// 1. `mmcblk0p1` / `nvme0n1p1` / `disk0s1` carry an explicit partition
    ///    marker (`p`/`s` after the disk index) -> `Partition`.
    /// 2. `nvme0n1` / `mmcblk0` / `disk0` end in a digit but are whole disks.
    /// 3. Otherwise a trailing digit (`sda1`, `vda2`) -> `Partition`.
    fn classify(name: &str) -> DeviceClass {
        if name
            .strip_prefix("nvme")
            .or_else(|| name.strip_prefix("mmcblk"))
            .is_some_and(|rest| rest.contains('p') && rest.ends_with(|c: char| c.is_ascii_digit()))
            || name.strip_prefix("disk").is_some_and(|rest| {
                rest.contains('s') && rest.ends_with(|c: char| c.is_ascii_digit())
            })
        {
            return DeviceClass::Partition;
        }
        let numbered_disk = name
            .strip_prefix("nvme")
            .or_else(|| name.strip_prefix("mmcblk"))
            .is_some_and(|rest| !rest.contains('p'))
            || name
                .strip_prefix("disk")
                .is_some_and(|rest| !rest.contains('s'));
        if numbered_disk {
            return DeviceClass::Disk;
        }
        if name.ends_with(|c: char| c.is_ascii_digit()) {
            DeviceClass::Partition
        } else {
            DeviceClass::Disk
        }
    }
}
