"""Compatibility entry point for the shared MathML-to-Office-Math structure converter."""

from opendoc_model.mathml import MATHML, OMML, mathml_to_omml

__all__ = ["MATHML", "OMML", "mathml_to_omml"]
