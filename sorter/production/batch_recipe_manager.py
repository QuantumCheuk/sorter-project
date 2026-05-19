"""
Batch Recipe Management System
===============================
Pre-defined quality profiles for different coffee origins and processing methods.
Allows operators to load preset recipes instead of manually configuring thresholds.

Usage:
    python -m sorter.production.batch_recipe_manager --list
    python -m sorter.production.batch_recipe_manager --load Ethiopian_Washed
    python -m sorter.production.batch_recipe_manager --apply --recipe Ethiopian_Washed --batch LOT-2026-0512-01
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
from pathlib import Path


RECIPE_DIR = Path(__file__).parent.parent / "recipes"


@dataclass
class ColorThresholds:
    """L*a*b* color thresholds per camera position."""
    top_L_min: float = 30.0
    top_L_max: float = 65.0
    top_a_min: float = 5.0
    top_a_max: float = 20.0
    top_b_min: float = 10.0
    top_b_max: float = 30.0
    bottom_L_min: float = 28.0
    bottom_L_max: float = 62.0
    bottom_a_min: float = 4.0
    bottom_a_max: float = 18.0
    bottom_b_min: float = 9.0
    bottom_b_max: float = 28.0


@dataclass
class WeightThresholds:
    """Weight classification thresholds (g/bean)."""
    undersize_g: float = 0.08
    light_g: float = 0.11
    normal_min_g: float = 0.12
    normal_max_g: float = 0.22
    heavy_g: float = 0.25
    oversize_g: float = 0.30


@dataclass
class MoistureThresholds:
    """Moisture content thresholds (wet basis %)."""
    too_dry_pct: float = 9.0
    target_min_pct: float = 10.5
    target_max_pct: float = 12.5
    too_wet_pct: float = 14.0


@dataclass
class DensityThresholds:
    """Density classification thresholds (g/mL)."""
    very_light: float = 0.55
    light: float = 0.60
    medium_min: float = 0.65
    medium_max: float = 0.76
    heavy: float = 0.80
    very_heavy: float = 0.85


@dataclass
class DefectWeights:
    """Severity weights for defect scoring (0-10)."""
    BROKEN: float = 9.0
    IMMATURE: float = 7.0
    FERRY: float = 8.0  # Fermented
    BLACK: float = 9.0
    OVERSIZE: float = 2.0
    UNDERSIZE: float = 3.0
    MOLD: float = 10.0
    INSECT: float = 10.0
    FOREIGN: float = 10.0


@dataclass
class QualityTargets:
    """Quality target parameters."""
    defect_rate_max_pct: float = 2.0  # Grade A
    color_score_min: float = 85.0
    weight_cv_max: float = 15.0  # Coefficient of variation
    moisture_target_pct: float = 11.0
    batch_size_kg: float = 0.250  # Portion size for roaster
    target_throughput_kg_h: float = 2.0


@dataclass
class BatchRecipe:
    """Complete batch recipe for a specific coffee origin/processing."""
    recipe_id: str
    name: str
    origin_country: str
    origin_region: str
    variety: str
    process: str
    harvest_year: int

    # Sensor thresholds
    color: ColorThresholds = field(default_factory=ColorThresholds)
    weight: WeightThresholds = field(default_factory=WeightThresholds)
    moisture: MoistureThresholds = field(default_factory=MoistureThresholds)
    density: DensityThresholds = field(default_factory=DensityThresholds)

    # Defect weights for quality scoring
    defect_weights: DefectWeights = field(default_factory=DefectWeights)

    # Quality targets
    quality: QualityTargets = field(default_factory=QualityTargets)

    # ML model path (relative to project root)
    ml_model_path: str = "models/sorter_ml_v1.tflite"

    # Notes for operator
    notes: str = ""

    # Recipe metadata
    created_at: str = ""
    version: str = "1.0"
    author: str = "HUSKY-SORTER-001"

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


# =============================================================================
# Pre-defined Recipes
# =============================================================================

RECIPES = {
    "Ethiopian_Washed": BatchRecipe(
        recipe_id="ETH-W-001",
        name="Ethiopian Washed (Yirgacheffe/Guji)",
        origin_country="埃塞俄比亚",
        origin_region="耶加雪菲/古吉",
        variety="Heirloom",
        process="水洗",
        harvest_year=2025,
        color=ColorThresholds(
            top_L_min=38.0, top_L_max=60.0,  # Bright, light color
            top_a_min=3.0, top_a_max=15.0,
            top_b_min=15.0, top_b_max=35.0,  # Yellowish (citrus notes)
            bottom_L_min=35.0, bottom_L_max=58.0,
            bottom_a_min=2.0, bottom_a_max=14.0,
            bottom_b_min=13.0, bottom_b_max=33.0,
        ),
        weight=WeightThresholds(
            undersize_g=0.08,
            light_g=0.11,
            normal_min_g=0.13,
            normal_max_g=0.20,
            heavy_g=0.24,
            oversize_g=0.28,
        ),
        moisture=MoistureThresholds(
            too_dry_pct=9.5,
            target_min_pct=10.5,
            target_max_pct=12.0,
            too_wet_pct=13.5,
        ),
        defect_weights=DefectWeights(
            BROKEN=9.0, IMMATURE=8.0, FERRY=9.0, BLACK=10.0,
            MOLD=10.0, INSECT=10.0, FOREIGN=10.0,
            OVERSIZE=1.5, UNDERSIZE=4.0,
        ),
        quality=QualityTargets(
            defect_rate_max_pct=1.5,
            color_score_min=88.0,
            batch_size_kg=0.250,
        ),
        notes="精品水洗豆，高端定位。颜色较浅是正常特征，不要误判为缺陷。发酵味=缺陷（必须剔除）。",
    ),

    "Ethiopian_Natural": BatchRecipe(
        recipe_id="ETH-N-001",
        name="Ethiopian Natural (Sidamo/Welega)",
        origin_country="埃塞俄比亚",
        origin_region="西达摩/瓦莱加",
        variety="Heirloom",
        process="日晒",
        harvest_year=2025,
        color=ColorThresholds(
            top_L_min=25.0, top_L_max=55.0,  # Darker, more variation
            top_a_min=5.0, top_a_max=22.0,
            top_b_min=8.0, top_b_max=32.0,
            bottom_L_min=22.0, bottom_L_max=52.0,
            bottom_a_min=4.0, bottom_a_max=20.0,
            bottom_b_min=7.0, bottom_b_max=30.0,
        ),
        weight=WeightThresholds(
            undersize_g=0.08,
            light_g=0.10,
            normal_min_g=0.12,
            normal_max_g=0.22,
            heavy_g=0.26,
            oversize_g=0.30,
        ),
        moisture=MoistureThresholds(
            too_dry_pct=8.5,
            target_min_pct=10.0,
            target_max_pct=13.0,
            too_wet_pct=14.5,
        ),
        defect_weights=DefectWeights(
            BROKEN=9.0, IMMATURE=8.0, FERRY=9.0, BLACK=10.0,
            MOLD=10.0, INSECT=10.0, FOREIGN=10.0,
            OVERSIZE=1.5, UNDERSIZE=4.0,
        ),
        quality=QualityTargets(
            defect_rate_max_pct=2.0,
            color_score_min=82.0,
            batch_size_kg=0.250,
        ),
        notes="日晒豆颜色深浅差异大，果肉残留正常。检测到过干或过湿需分级处理。",
    ),

    "Brazilian_Natural": BatchRecipe(
        recipe_id="BRA-N-001",
        name="Brazilian Natural (Cerrado/Minas)",
        origin_country="巴西",
        origin_region="喜拉多/米纳斯",
        variety="Bourbon/Catuai",
        process="日晒",
        harvest_year=2025,
        color=ColorThresholds(
            top_L_min=28.0, top_L_max=58.0,
            top_a_min=6.0, top_a_max=20.0,
            top_b_min=10.0, top_b_max=30.0,
            bottom_L_min=25.0, bottom_L_max=55.0,
            bottom_a_min=5.0, bottom_a_max=18.0,
            bottom_b_min=9.0, bottom_b_max=28.0,
        ),
        weight=WeightThresholds(
            undersize_g=0.09,
            light_g=0.12,
            normal_min_g=0.14,
            normal_max_g=0.24,
            heavy_g=0.28,
            oversize_g=0.32,
        ),
        moisture=MoistureThresholds(
            too_dry_pct=9.0,
            target_min_pct=10.5,
            target_max_pct=12.5,
            too_wet_pct=14.0,
        ),
        defect_weights=DefectWeights(
            BROKEN=8.0, IMMATURE=6.0, FERRY=8.0, BLACK=9.0,
            MOLD=10.0, INSECT=10.0, FOREIGN=10.0,
            OVERSIZE=2.0, UNDERSIZE=3.5,
        ),
        quality=QualityTargets(
            defect_rate_max_pct=3.0,
            color_score_min=80.0,
            batch_size_kg=0.250,
        ),
        notes="巴西豆普遍颗粒较大、密度高。接受稍大的oversize，允许更高缺陷率（商业豆定位）。",
    ),

    "Colombian_Washed": BatchRecipe(
        recipe_id="COL-W-001",
        name="Colombian Washed (Huila/Nariño)",
        origin_country="哥伦比亚",
        origin_region="惠兰/娜玲妞",
        variety="Caturra/Colombia",
        process="水洗",
        harvest_year=2025,
        color=ColorThresholds(
            top_L_min=32.0, top_L_max=60.0,
            top_a_min=4.0, top_a_max=18.0,
            top_b_min=12.0, top_b_max=32.0,
            bottom_L_min=30.0, bottom_L_max=57.0,
            bottom_a_min=3.0, bottom_a_max=16.0,
            bottom_b_min=10.0, bottom_b_max=30.0,
        ),
        weight=WeightThresholds(
            undersize_g=0.08,
            light_g=0.11,
            normal_min_g=0.13,
            normal_max_g=0.22,
            heavy_g=0.26,
            oversize_g=0.30,
        ),
        moisture=MoistureThresholds(
            too_dry_pct=9.5,
            target_min_pct=10.5,
            target_max_pct=12.0,
            too_wet_pct=13.5,
        ),
        defect_weights=DefectWeights(
            BROKEN=9.0, IMMATURE=7.0, FERRY=9.0, BLACK=10.0,
            MOLD=10.0, INSECT=10.0, FOREIGN=10.0,
            OVERSIZE=2.0, UNDERSIZE=3.5,
        ),
        quality=QualityTargets(
            defect_rate_max_pct=2.0,
            color_score_min=85.0,
            batch_size_kg=0.250,
        ),
        notes="哥伦比亚豆均衡度高，颜色一致性较好。水分控制严格（高海拔种植）。",
    ),

    "Kenyan_Washed": BatchRecipe(
        recipe_id="KEN-W-001",
        name="Kenyan Washed (AA/AB)",
        origin_country="肯尼亚",
        origin_region="涅里/基里尼亚加",
        variety="SL28/SL34/Batian",
        process="水洗",
        harvest_year=2025,
        color=ColorThresholds(
            top_L_min=35.0, top_L_max=62.0,  # Very bright, acidic
            top_a_min=3.0, top_a_max=14.0,
            top_b_min=14.0, top_b_max=36.0,
            bottom_L_min=32.0, bottom_L_max=59.0,
            bottom_a_min=2.0, bottom_a_max=13.0,
            bottom_b_min=12.0, bottom_b_max=34.0,
        ),
        weight=WeightThresholds(
            undersize_g=0.08,
            light_g=0.10,
            normal_min_g=0.12,
            normal_max_g=0.20,
            heavy_g=0.24,
            oversize_g=0.28,
        ),
        moisture=MoistureThresholds(
            too_dry_pct=9.5,
            target_min_pct=10.5,
            target_max_pct=12.0,
            too_wet_pct=13.5,
        ),
        defect_weights=DefectWeights(
            BROKEN=9.0, IMMATURE=8.0, FERRY=10.0, BLACK=10.0,
            MOLD=10.0, INSECT=10.0, FOREIGN=10.0,
            OVERSIZE=1.5, UNDERSIZE=4.0,
        ),
        quality=QualityTargets(
            defect_rate_max_pct=1.5,
            color_score_min=90.0,
            batch_size_kg=0.250,
        ),
        notes="肯尼亚AA高品质定位，严格剔除轻微缺陷。发酵过度检测优先级最高（肯尼亚特征缺陷）。",
    ),

    "Guatemalan_Washed": BatchRecipe(
        recipe_id="GUA-W-001",
        name="Guatemalan Washed (Antigua/Pacay)",
        origin_country="危地马拉",
        origin_region="安提瓜/阿卡特南戈",
        variety="Bourbon/Caturra",
        process="水洗",
        harvest_year=2025,
        color=ColorThresholds(
            top_L_min=30.0, top_L_max=58.0,
            top_a_min=5.0, top_a_max=19.0,
            top_b_min=11.0, top_b_max=31.0,
            bottom_L_min=28.0, bottom_L_max=55.0,
            bottom_a_min=4.0, bottom_a_max=17.0,
            bottom_b_min=10.0, bottom_b_max=29.0,
        ),
        weight=WeightThresholds(
            undersize_g=0.08,
            light_g=0.11,
            normal_min_g=0.13,
            normal_max_g=0.23,
            heavy_g=0.27,
            oversize_g=0.31,
        ),
        moisture=MoistureThresholds(
            too_dry_pct=9.0,
            target_min_pct=10.5,
            target_max_pct=12.5,
            too_wet_pct=14.0,
        ),
        defect_weights=DefectWeights(
            BROKEN=9.0, IMMATURE=7.0, FERRY=9.0, BLACK=10.0,
            MOLD=10.0, INSECT=10.0, FOREIGN=10.0,
            OVERSIZE=2.0, UNDERSIZE=3.5,
        ),
        quality=QualityTargets(
            defect_rate_max_pct=2.5,
            color_score_min=83.0,
            batch_size_kg=0.250,
        ),
        notes="安提瓜火山土壤豆，酸质好但偶有火山灰污染（ FOREIGN 需重点关注）。",
    ),

    "Costa_Rican_Washed": BatchRecipe(
        recipe_id="CRI-W-001",
        name="Costa Rican Washed (Tarrazú)",
        origin_country="哥斯达黎加",
        origin_region="塔拉珠",
        variety="Caturra/Geisha",
        process="水洗",
        harvest_year=2025,
        color=ColorThresholds(
            top_L_min=33.0, top_L_max=60.0,
            top_a_min=4.0, top_a_max=17.0,
            top_b_min=12.0, top_b_max=32.0,
            bottom_L_min=31.0, bottom_L_max=57.0,
            bottom_a_min=3.0, bottom_a_max=15.0,
            bottom_b_min=10.0, bottom_b_max=30.0,
        ),
        weight=WeightThresholds(
            undersize_g=0.08,
            light_g=0.11,
            normal_min_g=0.13,
            normal_max_g=0.21,
            heavy_g=0.25,
            oversize_g=0.29,
        ),
        moisture=MoistureThresholds(
            too_dry_pct=9.5,
            target_min_pct=10.5,
            target_max_pct=12.0,
            too_wet_pct=13.5,
        ),
        defect_weights=DefectWeights(
            BROKEN=9.0, IMMATURE=7.0, FERRY=9.0, BLACK=10.0,
            MOLD=10.0, INSECT=10.0, FOREIGN=10.0,
            OVERSIZE=2.0, UNDERSIZE=3.5,
        ),
        quality=QualityTargets(
            defect_rate_max_pct=2.0,
            color_score_min=85.0,
            batch_size_kg=0.250,
        ),
        notes="哥斯达黎加精品豆，Geisha品种有特殊花香特征，颜色偏浅是正常表现。",
    ),

    "Yemen_Natural": BatchRecipe(
        recipe_id="YEM-N-001",
        name="Yemen Natural (Haraz/Hirazi)",
        origin_country="也门",
        origin_region="哈拉兹/马达里",
        variety="Typica/Heirloom",
        process="日晒（传统）",
        harvest_year=2025,
        color=ColorThresholds(
            top_L_min=20.0, top_L_max=50.0,  # Very dark, rustic
            top_a_min=6.0, top_a_max=24.0,
            top_b_min=5.0, top_b_max=28.0,
            bottom_L_min=18.0, bottom_L_max=48.0,
            bottom_a_min=5.0, bottom_a_max=22.0,
            bottom_b_min=4.0, bottom_b_max=26.0,
        ),
        weight=WeightThresholds(
            undersize_g=0.07,
            light_g=0.10,
            normal_min_g=0.11,
            normal_max_g=0.20,
            heavy_g=0.24,
            oversize_g=0.28,
        ),
        moisture=MoistureThresholds(
            too_dry_pct=8.0,
            target_min_pct=9.5,
            target_max_pct=13.0,
            too_wet_pct=14.5,
        ),
        defect_weights=DefectWeights(
            BROKEN=9.0, IMMATURE=7.0, FERRY=9.0, BLACK=10.0,
            MOLD=10.0, INSECT=10.0, FOREIGN=10.0,
            OVERSIZE=1.5, UNDERSIZE=4.0,
        ),
        quality=QualityTargets(
            defect_rate_max_pct=3.0,
            color_score_min=78.0,
            batch_size_kg=0.250,
        ),
        notes="也门咖啡稀缺度高，颜色深浅不一不代表缺陷。允许更宽泛的颜色范围，重点剔除MOLD/INSECT/FOREIGN。",
    ),

    "Default_Commercial": BatchRecipe(
        recipe_id="COM-001",
        name="Commercial Blend (Default)",
        origin_country="混合",
        origin_region="商业豆",
        variety="Mixed",
        process="Mixed",
        harvest_year=2025,
        color=ColorThresholds(
            top_L_min=25.0, top_L_max=65.0,
            top_a_min=3.0, top_a_max=22.0,
            top_b_min=8.0, top_b_max=35.0,
            bottom_L_min=22.0, bottom_L_max=62.0,
            bottom_a_min=2.0, bottom_a_max=20.0,
            bottom_b_min=7.0, bottom_b_max=33.0,
        ),
        weight=WeightThresholds(
            undersize_g=0.08,
            light_g=0.10,
            normal_min_g=0.12,
            normal_max_g=0.25,
            heavy_g=0.28,
            oversize_g=0.32,
        ),
        moisture=MoistureThresholds(
            too_dry_pct=9.0,
            target_min_pct=10.0,
            target_max_pct=13.0,
            too_wet_pct=14.5,
        ),
        defect_weights=DefectWeights(
            BROKEN=8.0, IMMATURE=6.0, FERRY=8.0, BLACK=9.0,
            MOLD=10.0, INSECT=10.0, FOREIGN=10.0,
            OVERSIZE=2.5, UNDERSIZE=3.0,
        ),
        quality=QualityTargets(
            defect_rate_max_pct=5.0,
            color_score_min=75.0,
            batch_size_kg=0.250,
        ),
        notes="商业豆通用配置。允许较大颜色和重量变异，重点剔除霉变/虫蛀/异物。",
    ),
}


class RecipeManager:
    """Manages batch recipes - load, save, apply, validate."""

    def __init__(self, recipe_dir: Path = RECIPE_DIR):
        self.recipe_dir = recipe_dir
        self.recipe_dir.mkdir(parents=True, exist_ok=True)
        self._active_recipe: Optional[BatchRecipe] = None
        self._active_batch_id: Optional[str] = None

    def list_recipes(self) -> list:
        """List all available recipe IDs."""
        return list(RECIPES.keys())

    def get_recipe(self, recipe_id: str) -> Optional[BatchRecipe]:
        """Get recipe by ID."""
        return RECIPES.get(recipe_id)

    def load_recipe(self, recipe_id: str) -> Optional[BatchRecipe]:
        """Load a recipe into active memory."""
        recipe = RECIPES.get(recipe_id)
        if recipe:
            self._active_recipe = recipe
            return recipe
        return None

    def apply_recipe(self, recipe_id: str, batch_id: str = None) -> dict:
        """Load recipe and generate config for SorterController."""
        recipe = self.load_recipe(recipe_id)
        if not recipe:
            return {"status": "error", "message": f"Recipe {recipe_id} not found"}

        self._active_batch_id = batch_id

        # Generate config dict compatible with SorterController
        config = {
            "batch_metadata": {
                "batch_id": batch_id or f"BATCH-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "recipe_id": recipe.recipe_id,
                "recipe_name": recipe.name,
                "origin_country": recipe.origin_country,
                "origin_region": recipe.origin_region,
                "variety": recipe.variety,
                "process": recipe.process,
                "harvest_year": recipe.harvest_year,
                "loaded_at": datetime.now().isoformat(),
            },
            "quality_thresholds": {
                "color_top": asdict(recipe.color),
                "color_bottom": asdict(recipe.color),
                "weight": asdict(recipe.weight),
                "moisture": asdict(recipe.moisture),
                "density": asdict(recipe.density),
                "defect_weights": asdict(recipe.defect_weights),
            },
            "quality_targets": asdict(recipe.quality),
            "ml_model_path": recipe.ml_model_path,
            "notes": recipe.notes,
        }
        return config

    def save_active_config(self, path: Path = None) -> Path:
        """Save currently active config to JSON file."""
        if not self._active_recipe:
            raise ValueError("No active recipe loaded")

        if path is None:
            batch_id = self._active_batch_id or "NO-BATCH"
            path = self.recipe_dir / f"config_{batch_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        config = self.apply_recipe(self._active_recipe.recipe_id, self._active_batch_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return path

    def validate_recipe(self, recipe_id: str) -> dict:
        """Validate recipe completeness and consistency."""
        recipe = RECIPES.get(recipe_id)
        if not recipe:
            return {"valid": False, "errors": [f"Recipe {recipe_id} not found"]}

        errors = []
        warnings = []

        # Check required fields (P-010: non-empty validation)
        if not recipe.recipe_id:
            errors.append("Missing recipe_id")
        if not recipe.origin_country:
            errors.append("Missing origin_country")
        if not recipe.variety:
            errors.append("Missing variety")
        if not recipe.process:
            errors.append("Missing process")

        # Check threshold consistency (P1-15: full range ordering validation)
        if recipe.color.top_L_min >= recipe.color.top_L_max:
            errors.append(f"Color top L range invalid: {recipe.color.top_L_min} >= {recipe.color.top_L_max}")

        if recipe.weight.normal_min_g >= recipe.weight.normal_max_g:
            errors.append(f"Weight normal range invalid: {recipe.weight.normal_min_g} >= {recipe.weight.normal_max_g}")

        # P1-15 fix: validate full weight range ordering
        wt = recipe.weight
        if wt.undersize_g >= wt.light_g:
            errors.append(f"Weight undersize >= light: {wt.undersize_g} >= {wt.light_g}")
        if wt.light_g >= wt.normal_min_g:
            errors.append(f"Weight light >= normal_min: {wt.light_g} >= {wt.normal_min_g}")
        if wt.normal_max_g >= wt.heavy_g:
            errors.append(f"Weight normal_max >= heavy: {wt.normal_max_g} >= {wt.heavy_g}")
        if wt.heavy_g >= wt.oversize_g:
            errors.append(f"Weight heavy >= oversize: {wt.heavy_g} >= {wt.oversize_g}")

        if recipe.moisture.target_min_pct >= recipe.moisture.target_max_pct:
            errors.append(f"Moisture target range invalid")

        # P1-15 fix: validate moisture range ordering
        mt = recipe.moisture
        if mt.too_dry_pct >= mt.target_min_pct:
            errors.append(f"Moisture too_dry >= target_min: {mt.too_dry_pct} >= {mt.target_min_pct}")
        if mt.target_max_pct >= mt.too_wet_pct:
            errors.append(f"Moisture target_max >= too_wet: {mt.target_max_pct} >= {mt.too_wet_pct}")

        # Density range ordering
        dt = recipe.density
        if dt.light >= dt.medium_min:
            errors.append(f"Density light >= medium_min: {dt.light} >= {dt.medium_min}")
        if dt.medium_min >= dt.medium_max:
            errors.append(f"Density medium range invalid: {dt.medium_min} >= {dt.medium_max}")
        if dt.medium_max >= dt.heavy:
            errors.append(f"Density medium_max >= heavy: {dt.medium_max} >= {dt.heavy}")

        # Check quality targets
        if recipe.quality.defect_rate_max_pct > 10:
            warnings.append(f"High defect rate threshold: {recipe.quality.defect_rate_max_pct}%")

        if recipe.quality.batch_size_kg <= 0 or recipe.quality.batch_size_kg > 10:
            errors.append(f"Batch size out of reasonable range: {recipe.quality.batch_size_kg}kg")

        return {
            "valid": len(errors) == 0,
            "recipe_id": recipe_id,
            "errors": errors,
            "warnings": warnings,
        }

    def get_active_recipe(self) -> Optional[BatchRecipe]:
        """Get currently loaded recipe."""
        return self._active_recipe

    def export_all_recipes(self) -> Path:
        """Export all recipes to a single JSON file for backup."""
        output_path = self.recipe_dir / f"all_recipes_{datetime.now().strftime('%Y%m%d')}.json"
        data = {rid: asdict(recipe) for rid, recipe in RECIPES.items()}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return output_path


def print_recipe_summary(recipe: BatchRecipe) -> str:
    """Format recipe as readable summary."""
    lines = [
        f"\n{'='*60}",
        f"Recipe: {recipe.name}",
        f"{'='*60}",
        f"ID:      {recipe.recipe_id}",
        f"Origin:  {recipe.origin_country} > {recipe.origin_region}",
        f"Variety: {recipe.variety} ({recipe.process})",
        f"Harvest: {recipe.harvest_year}",
        f"",
        f"Quality Targets:",
        f"  Defect rate max:  {recipe.quality.defect_rate_max_pct}%",
        f"  Color score min:   {recipe.quality.color_score_min}",
        f"  Batch size:        {recipe.quality.batch_size_kg*1000:.0f}g",
        f"  Throughput target: {recipe.quality.target_throughput_kg_h}kg/h",
        f"",
        f"Thresholds:",
        f"  Weight:  {recipe.weight.undersize_g:.2f}-{recipe.weight.normal_min_g:.2f}(light) "
        f"{recipe.weight.normal_min_g:.2f}-{recipe.weight.normal_max_g:.2f}(normal) "
        f"{recipe.weight.heavy_g:.2f}+(heavy)",
        f"  Moisture: {recipe.moisture.target_min_pct}-{recipe.moisture.target_max_pct}% (target)",
        f"  Density:  {recipe.density.light}-{recipe.density.medium_min}(light) "
        f"{recipe.density.medium_min}-{recipe.density.medium_max}(medium) "
        f"{recipe.density.heavy}+(heavy)",
        f"",
        f"Notes: {recipe.notes}",
    ]
    return "\n".join(lines)


def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Batch Recipe Manager for HUSKY-SORTER-001")
    parser.add_argument("--list", action="store_true", help="List all available recipes")
    parser.add_argument("--show", metavar="RECIPE_ID", help="Show recipe details")
    parser.add_argument("--load", metavar="RECIPE_ID", help="Load recipe into active memory")
    parser.add_argument("--apply", action="store_true", help="Apply loaded recipe and print config")
    parser.add_argument("--recipe", metavar="RECIPE_ID", help="Recipe to apply")
    parser.add_argument("--batch", metavar="BATCH_ID", help="Batch ID for config")
    parser.add_argument("--validate", metavar="RECIPE_ID", help="Validate recipe")
    parser.add_argument("--export", action="store_true", help="Export all recipes to JSON")

    args = parser.parse_args()
    manager = RecipeManager()

    if args.list:
        print("\nAvailable Recipes:")
        print("-" * 40)
        for rid in sorted(RECIPES.keys()):
            recipe = RECIPES[rid]
            print(f"  {rid:20s} - {recipe.name}")
            print(f"                        {recipe.origin_country} / {recipe.variety} / {recipe.process}")
        print(f"\nTotal: {len(RECIPES)} recipes")

    elif args.show:
        recipe = manager.get_recipe(args.show)
        if recipe:
            print(print_recipe_summary(recipe))
        else:
            print(f"Recipe '{args.show}' not found")

    elif args.load:
        recipe = manager.load_recipe(args.load)
        if recipe:
            print(f"✓ Loaded recipe: {recipe.name}")
        else:
            print(f"✗ Recipe '{args.load}' not found")

    elif args.apply:
        recipe_id = args.recipe or (manager.get_active_recipe().recipe_id if manager.get_active_recipe() else None)
        if not recipe_id:
            print("No recipe loaded. Use --load RECIPE_ID first.")
            return
        config = manager.apply_recipe(recipe_id, args.batch)
        print(json.dumps(config, indent=2, ensure_ascii=False))

    elif args.validate:
        result = manager.validate_recipe(args.validate)
        print(f"\nValidation: {result['recipe_id']}")
        print(f"Valid: {result['valid']}")
        if result['errors']:
            print("Errors:")
            for e in result['errors']:
                print(f"  ✗ {e}")
        if result['warnings']:
            print("Warnings:")
            for w in result['warnings']:
                print(f"  ⚠ {w}")

    elif args.export:
        path = manager.export_all_recipes()
        print(f"✓ Exported all recipes to: {path}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()