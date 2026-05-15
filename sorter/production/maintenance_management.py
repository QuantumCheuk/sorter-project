#!/usr/bin/env python3
"""
Maintenance & Reliability Management System - v1.0
Comprehensive maintenance operations platform for HUSKY-SORTER-001.
"""
import json, math, random, statistics, sys, time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class MT(str, Enum): PREVENTIVE='preventive'; CORRECTIVE='corrective'; PREDICTIVE='predictive'; CALIBRATION='calibration'; INSPECTION='inspection'
class Priority(str, Enum): CRITICAL='critical'; HIGH='high'; MEDIUM='medium'; LOW='low'
class MS(str, Enum): PENDING='pending'; IN_PROGRESS='in_progress'; COMPLETED='completed'; CANCELLED='cancelled'; OVERDUE='overdue'
class CC(str, Enum): MECHANICAL='mechanical'; ELECTRICAL='electrical'; ELECTRONIC='electronic'; PNEUMATIC='pneumatic'; STRUCTURAL='structural'

@dataclass
class Component:
    component_id: str; name: str; category: CC; location: str; failure_mode: str
    mtbf_hours: float; mtbf_reference: str; avg_repair_time_hours: float; parent_system: str
    spares_unit_cost: float; spares_quantity: int; critical_spares: bool
    replacement_interval_months: int; lubricant_required: bool; calibration_required: bool
    calibration_interval_days: int=0; last_calibration_date: Optional[str]=None
    next_calibration_date: Optional[str]=None; last_maintenance_date: Optional[str]=None; operating_hours: float=0.0

@dataclass
class MaintenanceTask:
    task_id: str; component_id: str; component_name: str
    maintenance_type: MT; priority: Priority; status: MS; description: str; created_date: str
    scheduled_date: Optional[str]=None; started_date: Optional[str]=None
    completed_date: Optional[str]=None; technician: Optional[str]=None
    labor_hours: float=0.0; repair_cost: float=0.0; downtime_hours: float=0.0
    corrective_action: Optional[str]=None; root_cause: Optional[str]=None; notes: Optional[str]=None

@dataclass
class MKPI:
    period: str; total_tasks: int=0; preventive_tasks: int=0; corrective_tasks: int=0
    calibration_tasks: int=0; total_labor_hours: float=0.0; total_repair_cost: float=0.0
    total_downtime_hours: float=0.0; mtbf_system_hours: float=0.0; mttr_avg_hours: float=0.0
    availability_pct: float=0.0; maintenance_cost_per_kg: float=0.0; overdue_tasks: int=0
    first_time_fix_rate: float=0.0

@dataclass
class SparePart:
    part_id: str; name: str; description: str; category: CC; unit_cost: float
    reorder_point: int; reorder_quantity: int; current_stock: int; lead_time_days: int
    supplier: str; supplier_part_number: str; compatible_components: List[str]

@dataclass
class Technician:
    technician_id: str; name: str; certification_level: str; skill_set: List[str]
    hourly_rate: float; available_hours_per_week: float
    current_workload_pct: float=0.0; active_tasks: int=0
    completed_tasks_this_month: int=0; avg_rating: float=5.0

@dataclass
class MSched:
    schedule_id: str; component_id: str; maintenance_type: MT; interval_days: int
    next_due_date: str; estimated_duration_hours: float; estimated_cost: float
    priority: Priority; description: str; procedure_reference: str=''
    parts_required: List[str]=field(default_factory=list); enabled: bool=True
