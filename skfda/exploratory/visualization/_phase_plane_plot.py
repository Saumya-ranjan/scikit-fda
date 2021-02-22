from typing import List, Optional, TypeVar

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from ...representation import FData

from ._utils import (
    _get_figure_and_axes,
    _set_figure_layout,
)

S = TypeVar('S', Figure, Axes, List[Axes])


class PhasePlanePlot:

    def __init__(
        self,
        fdata1: FData,
        fdata2: Optional[FData] = None,
    ) -> None:
        self.fdata1 = fdata1
        self.fdata2 = fdata2

    def plot(
        self,
        chart: Optional[S] = None,
        *,
        fig: Optional[Figure] = None,
        axes: Optional[List[Axes]] = None,
        **kwargs,
    ) -> Figure:
        fig, axes = _get_figure_and_axes(chart, fig, axes)

        if (
            self.fdata2 is not None
        ):
            if (
                self.fdata1.dim_domain == self.fdata2.dim_domain
                and self.fdata1.dim_codomain == self.fdata2.dim_codomain
                and self.fdata1.dim_domain == 1
                and self.fdata1.dim_codomain == 1
            ):
                self.fd_final = self.fdata1.concatenate(
                    self.fdata2, as_coordinates=True
                )
            else:
                raise ValueError(
                    "Error in data arguments",
                )
        else:
            self.fd_final = self.fdata1

        if (
            self.fd_final.dim_domain == 1
            and self.fd_final.dim_codomain == 2
        ):
            fig, axes = _set_figure_layout(
                fig, axes, dim=2, n_axes=1,
            )
            axes[0].plot(
                self.fd_final.data_matrix[0][:,0].tolist(),
                self.fd_final.data_matrix[0][:,1].tolist(),
                **kwargs,
            )
        else:
            raise ValueError(
                "Error in data arguments",
            )

        fig.suptitle("Phase-Plane Plot")
        axes[0].set_xlabel("Function 1")
        axes[0].set_ylabel("Function 2")

        return fig
