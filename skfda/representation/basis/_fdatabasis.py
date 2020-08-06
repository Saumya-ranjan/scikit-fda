from builtins import isinstance
import copy
import numbers
from typing import Any

import pandas.api.extensions

import numpy as np

from .. import grid
from ..._utils import constants, _int_to_real
from .._functional_data import FData


def _same_domain(one_domain_range, other_domain_range):
    return np.array_equal(one_domain_range, other_domain_range)


class FDataBasis(FData):
    r"""Basis representation of functional data.

    Class representation for functional data in the form of a set of basis
    functions multplied by a set of coefficients.

    .. math::
        f(x) = \sum_{k=1}{K}c_k\phi_k

    Where n is the number of basis functions, :math:`c = (c_1, c_2, ...,
    c_K)` the vector of coefficients and  :math:`\phi = (\phi_1, \phi_2,
    ..., \phi_K)` the basis function system.

    Attributes:
        basis (:obj:`Basis`): Basis function system.
        coefficients (numpy.darray): List or matrix of coefficients. Has to
            have the same length or number of columns as the number of basis
            function in the basis. If a matrix, each row contains the
            coefficients that multiplied by the basis functions produce each
            functional datum.
        domain_range (numpy.ndarray): 2 dimension matrix where each row
            contains the bounds of the interval in which the functional data
            is considered to exist for each one of the axies.
        dataset_name (str): name of the dataset.
        argument_names (tuple): tuple containing the names of the different
            arguments.
        coordinate_names (tuple): tuple containing the names of the different
            coordinate functions.
        extrapolation (str or Extrapolation): defines the default type of
            extrapolation. By default None, which does not apply any type of
            extrapolation. See `Extrapolation` for detailled information of the
            types of extrapolation.

    Examples:
        >>> from skfda.representation.basis import FDataBasis, Monomial
        >>>
        >>> basis = Monomial(n_basis=4)
        >>> coefficients = [1, 1, 3, .5]
        >>> FDataBasis(basis, coefficients)
        FDataBasis(
            basis=Monomial(domain_range=((0, 1),), n_basis=4),
            coefficients=[[ 1.   1.   3.   0.5]],
            ...)

    """
    class _CoordinateIterator:
        """Internal class to iterate through the image coordinates.

        Dummy object. Should be change to support multidimensional objects.

        """

        def __init__(self, fdatabasis):
            """Create an iterator through the image coordinates."""
            self._fdatabasis = fdatabasis

        def __iter__(self):
            """Return an iterator through the image coordinates."""

            for i in range(len(self)):
                yield self[i]

        def __getitem__(self, key):
            """Get a specific coordinate."""

            return self._fdatabasis.basis._coordinate(self._fdatabasis, key)

        def __len__(self):
            """Return the number of coordinates."""
            return self._fdatabasis.dim_codomain

    def __init__(self, basis, coefficients, *, dataset_label=None,
                 dataset_name=None,
                 axes_labels=None, argument_names=None,
                 coordinate_names=None,
                 sample_names=None,
                 extrapolation=None):
        """Construct a FDataBasis object.

        Args:
            basis (:obj:`Basis`): Basis function system.
            coefficients (array_like): List or matrix of coefficients. Has to
                have the same length or number of columns as the number of
                basis function in the basis.
        """
        coefficients = _int_to_real(np.atleast_2d(coefficients))
        if coefficients.shape[1] != basis.n_basis:
            raise ValueError("The length or number of columns of coefficients "
                             "has to be the same equal to the number of "
                             "elements of the basis.")
        self.basis = basis
        self.coefficients = coefficients

        super().__init__(extrapolation=extrapolation,
                         dataset_label=dataset_label,
                         dataset_name=dataset_name,
                         axes_labels=axes_labels,
                         argument_names=argument_names,
                         coordinate_names=coordinate_names,
                         sample_names=sample_names)

    @classmethod
    def from_data(cls, data_matrix, sample_points, basis,
                  method='cholesky'):
        r"""Transform raw data to a smooth functional form.

        Takes functional data in a discrete form and makes an approximates it
        to the closest function that can be generated by the basis. This
        function does not attempt to smooth the original data. If smoothing
        is desired, it is better to use :class:`BasisSmoother`.

        The fit is made so as to reduce the sum of squared errors
        [RS05-5-2-5]_:

        .. math::

            SSE(c) = (y - \Phi c)' (y - \Phi c)

        where :math:`y` is the vector or matrix of observations, :math:`\Phi`
        the matrix whose columns are the basis functions evaluated at the
        sampling points and :math:`c` the coefficient vector or matrix to be
        estimated.

        By deriving the first formula we obtain the closed formed of the
        estimated coefficients matrix:

        .. math::

            \hat{c} = \left( \Phi' \Phi \right)^{-1} \Phi' y

        The solution of this matrix equation is done using the cholesky
        method for the resolution of a LS problem. If this method throughs a
        rounding error warning you may want to use the QR factorisation that
        is more numerically stable despite being more expensive to compute.
        [RS05-5-2-7]_

        Args:
            data_matrix (array_like): List or matrix containing the
                observations. If a matrix each row represents a single
                functional datum and the columns the different observations.
            sample_points (array_like): Values of the domain where the previous
                data were taken.
            basis: (Basis): Basis used.
            method (str): Algorithm used for calculating the coefficients using
                the least squares method. The values admitted are 'cholesky'
                and 'qr' for Cholesky and QR factorisation methods
                respectively.

        Returns:
            FDataBasis: Represention of the data in a functional form as
                product of coefficients by basis functions.

        Examples:
            >>> import numpy as np
            >>> t = np.linspace(0, 1, 5)
            >>> x = np.sin(2 * np.pi * t) + np.cos(2 * np.pi * t) + 2
            >>> x
            array([ 3.,  3.,  1.,  1.,  3.])

            >>> from skfda.representation.basis import FDataBasis, Fourier
            >>> basis = Fourier((0, 1), n_basis=3)
            >>> fd = FDataBasis.from_data(x, t, basis)
            >>> fd.coefficients.round(2)
            array([[ 2.  , 0.71, 0.71]])

        References:
            .. [RS05-5-2-5] Ramsay, J., Silverman, B. W. (2005). How spline
                smooths are computed. In *Functional Data Analysis*
                (pp. 86-87). Springer.

            .. [RS05-5-2-7] Ramsay, J., Silverman, B. W. (2005). HSpline
                smoothing as an augmented least squares problem. In *Functional
                Data Analysis* (pp. 86-87). Springer.

        """
        from ...preprocessing.smoothing import BasisSmoother
        from ..grid import FDataGrid

        # n is the samples
        # m is the observations
        # k is the number of elements of the basis

        # Each sample in a column (m x n)
        data_matrix = np.atleast_2d(data_matrix)

        fd = FDataGrid(data_matrix=data_matrix, sample_points=sample_points)

        smoother = BasisSmoother(
            basis=basis,
            method=method,
            return_basis=True)

        return smoother.fit_transform(fd)

    @property
    def n_samples(self):
        """Return number of samples."""
        return self.coefficients.shape[0]

    @property
    def dim_domain(self):
        """Return number of dimensions of the domain."""

        return self.basis.dim_domain

    @property
    def dim_codomain(self):
        """Return number of dimensions of the image."""

        return self.basis.dim_codomain

    @property
    def coordinates(self):
        r"""Return a component of the FDataBasis.

        If the functional object contains samples
        :math:`f: \mathbb{R}^n \rightarrow \mathbb{R}^d`, this object allows
        a component of the vector :math:`f = (f_1, ..., f_d)`.


        Todo:
            By the moment, only unidimensional objects are supported in basis
            form.

        """

        return FDataBasis._CoordinateIterator(self)

    @property
    def n_basis(self):
        """Return number of basis."""
        return self.basis.n_basis

    @property
    def domain_range(self):

        return self.basis.domain_range

    def _evaluate(self, eval_points,  *, aligned=True):

        if aligned:

            # Each row contains the values of one element of the basis
            basis_values = self.basis.evaluate(eval_points)

            res = np.tensordot(self.coefficients, basis_values, axes=(1, 0))

            return res.reshape(
                (self.n_samples, len(eval_points), self.dim_codomain))

        else:

            res_matrix = np.empty(
                (self.n_samples, eval_points.shape[1], self.dim_codomain))

            for i in range(self.n_samples):
                basis_values = self.basis.evaluate(eval_points[i])

                values = self.coefficients[i] * basis_values.T
                np.sum(values.T, axis=0, out=res_matrix[i])

            return res_matrix

    def shift(self, shifts, *, restrict_domain=False, extrapolation=None,
              eval_points=None, **kwargs):
        r"""Perform a shift of the curves.

        Args:
            shifts (array_like or numeric): List with the the shift
                corresponding for each sample or numeric with the shift to
                apply to all samples.
            restrict_domain (bool, optional): If True restricts the domain to
                avoid evaluate points outside the domain using extrapolation.
                Defaults uses extrapolation.
            extrapolation (str or Extrapolation, optional): Controls the
                extrapolation mode for elements outside the domain range.
                By default uses the method defined in fd. See extrapolation to
                more information.
            eval_points (array_like, optional): Set of points where
                the functions are evaluated to obtain the discrete
                representation of the object to operate. If an empty list is
                passed it calls numpy.linspace with bounds equal to the ones
                defined in fd.domain_range and the number of points the maximum
                between 201 and 10 times the number of basis plus 1.
            **kwargs: Keyword arguments to be passed to :meth:`from_data`.

        Returns:
            :obj:`FDataBasis` with the shifted data.
        """

        if self.dim_codomain > 1 or self.dim_domain > 1:
            raise ValueError

        domain_range = self.domain_range[0]

        if eval_points is None:  # Grid to discretize the function
            nfine = max(self.n_basis * 10 + 1, constants.N_POINTS_COARSE_MESH)
            eval_points = np.linspace(*domain_range, nfine)
        else:
            eval_points = np.asarray(eval_points)

        if np.isscalar(shifts):  # Special case, all curves with same shift

            _basis = self.basis.rescale((domain_range[0] + shifts,
                                         domain_range[1] + shifts))

            return FDataBasis.from_data(self.evaluate(eval_points),
                                        eval_points + shifts,
                                        _basis, **kwargs)

        elif len(shifts) != self.n_samples:
            raise ValueError(f"shifts vector ({len(shifts)}) must have the "
                             f"same length than the number of samples "
                             f"({self.n_samples})")

        if restrict_domain:
            a = domain_range[0] - min(np.min(shifts), 0)
            b = domain_range[1] - max(np.max(shifts), 0)
            domain = (a, b)
            eval_points = eval_points[
                np.logical_and(eval_points >= a,
                               eval_points <= b)]
        else:
            domain = domain_range

        points_shifted = np.outer(np.ones(self.n_samples),
                                  eval_points)

        points_shifted += np.atleast_2d(shifts).T

        # Matrix of shifted values
        _data_matrix = self(points_shifted,
                            aligned=False,
                            extrapolation=extrapolation)[..., 0]

        _basis = self.basis.rescale(domain)

        return FDataBasis.from_data(_data_matrix, eval_points,
                                    _basis, **kwargs)

    def derivative(self, *, order=1):
        r"""Differentiate a FDataBasis object.


        Args:
            order (int, optional): Order of the derivative. Defaults to one.
        """

        if order < 0:
            raise ValueError("order only takes non-negative integer values.")

        if order == 0:
            return self.copy()

        basis, coefficients = self.basis._derivative_basis_and_coefs(
            self.coefficients, order)

        return FDataBasis(basis, coefficients)

    def mean(self, weights=None):
        """Compute the mean of all the samples in a FDataBasis object.

        Returns:
            :obj:`FDataBasis`: A FDataBais object with just one sample
            representing the mean of all the samples in the original
            FDataBasis object.

        Examples:

            >>> from skfda.representation.basis import FDataBasis, Monomial
            >>> basis = Monomial(n_basis=4)
            >>> coefficients = [[0.5, 1, 2, .5], [1.5, 1, 4, .5]]
            >>> FDataBasis(basis, coefficients).mean()
            FDataBasis(
                basis=Monomial(domain_range=((0, 1),), n_basis=4),
                coefficients=[[ 1.  1.  3.  0.5]],
                ...)

        """

        if weights is not None:
            return self.copy(coefficients=np.average(self.coefficients,
                                                     weights=weights,
                                                     axis=0
                                                     )[np.newaxis, ...],
                             sample_names=("mean",)
                             )

        return self.copy(coefficients=np.mean(self.coefficients, axis=0),
                         sample_names=("mean",))

    def gmean(self, eval_points=None):
        """Compute the geometric mean of the functional data object.

        A numerical approach its used. The object its transformed into its
        discrete representation and then the geometric mean is computed and
        then the object is taken back to the basis representation.

        Args:
            eval_points (array_like, optional): Set of points where the
                functions are evaluated to obtain the discrete
                representation of the object. If none are passed it calls
                numpy.linspace with bounds equal to the ones defined in
                self.domain_range and the number of points the maximum
                between 501 and 10 times the number of basis.

        Returns:
            FDataBasis: Geometric mean of the original object.

        """
        return self.to_grid(eval_points).gmean().to_basis(self.basis)

    def var(self, eval_points=None):
        """Compute the variance of the functional data object.

        A numerical approach its used. The object its transformed into its
        discrete representation and then the variance is computed and
        then the object is taken back to the basis representation.

        Args:
            eval_points (array_like, optional): Set of points where the
                functions are evaluated to obtain the discrete
                representation of the object. If none are passed it calls
                numpy.linspace with bounds equal to the ones defined in
                self.domain_range and the number of points the maximum
                between 501 and 10 times the number of basis.

        Returns:
            FDataBasis: Variance of the original object.

        """
        return self.to_grid(eval_points).var().to_basis(self.basis)

    def cov(self, eval_points=None):
        """Compute the covariance of the functional data object.

        A numerical approach its used. The object its transformed into its
        discrete representation and then the covariance matrix is computed.

        Args:
            eval_points (array_like, optional): Set of points where the
                functions are evaluated to obtain the discrete
                representation of the object. If none are passed it calls
                numpy.linspace with bounds equal to the ones defined in
                self.domain_range and the number of points the maximum
                between 501 and 10 times the number of basis.

        Returns:
            numpy.darray: Matrix of covariances.

        """
        return self.to_grid(eval_points).cov()

    def to_grid(self, sample_points=None):
        """Return the discrete representation of the object.

        Args:
            sample_points (array_like, optional): Points per axis where the
                functions are evaluated. If none are passed it calls
                numpy.linspace with bounds equal to the ones defined in
                self.domain_range and the number of points the maximum
                between 501 and 10 times the number of basis.

        Returns:
              FDataGrid: Discrete representation of the functional data
              object.

        Examples:

            >>> from skfda.representation.basis import FDataBasis, Monomial
            >>> fd = FDataBasis(coefficients=[[1, 1, 1], [1, 0, 1]],
            ...                 basis=Monomial((0,5), n_basis=3))
            >>> fd.to_grid([0, 1, 2])
            FDataGrid(
                array([[[ 1.],
                        [ 3.],
                        [ 7.]],
                       [[ 1.],
                        [ 2.],
                        [ 5.]]]),
                sample_points=(array([0, 1, 2]),),
                domain_range=((0, 5),),
                ...)

        """

        if sample_points is None:
            npoints = max(constants.N_POINTS_FINE_MESH,
                          constants.BASIS_MIN_FACTOR * self.n_basis)
            sample_points = [np.linspace(*r, npoints)
                             for r in self.domain_range]

        return grid.FDataGrid(self.evaluate(sample_points, grid=True),
                              sample_points=sample_points,
                              domain_range=self.domain_range)

    def to_basis(self, basis, eval_points=None, **kwargs):
        """Return the basis representation of the object.

        Args:
            basis(Basis): basis object in which the functional data are
                going to be represented.
            **kwargs: keyword arguments to be passed to
                FDataBasis.from_data().

        Returns:
            FDataBasis: Basis representation of the funtional data
            object.
        """

        if basis == self.basis:
            return self.copy()

        return self.to_grid(eval_points=eval_points).to_basis(basis, **kwargs)

    def copy(self, *, basis=None, coefficients=None,
             dataset_name=None,
             argument_names=None,
             coordinate_names=None,
             sample_names=None,
             extrapolation=None):
        """FDataBasis copy"""

        if basis is None:
            basis = copy.deepcopy(self.basis)

        if coefficients is None:
            coefficients = self.coefficients

        if dataset_name is None:
            dataset_name = self.dataset_name

        if argument_names is None:
            # Tuple, immutable
            argument_names = self.argument_names

        if coordinate_names is None:
            # Tuple, immutable
            coordinate_names = self.coordinate_names

        if sample_names is None:
            # Tuple, immutable
            sample_names = self.sample_names

        if extrapolation is None:
            extrapolation = self.extrapolation

        return FDataBasis(basis, coefficients,
                          dataset_name=dataset_name,
                          argument_names=argument_names,
                          coordinate_names=coordinate_names,
                          sample_names=sample_names,
                          extrapolation=extrapolation)

    def times(self, other):
        """"Provides a numerical approximation of the multiplication between
            an FDataObject to other object

        Args:
            other (int, list, FDataBasis): Object to multiply with the
                                           FDataBasis object.

                * int: Multiplies all samples with the value
                * list: multiply each values with the samples respectively.
                    Length should match with FDataBasis samples
                * FDataBasis: if there is one sample it multiplies this with
                    all the samples in the object. If not, it multiplies each
                    sample respectively. Samples should match

        Returns:
            (FDataBasis): FDataBasis object containing the multiplication

        """
        if isinstance(other, FDataBasis):

            if not _same_domain(self.domain_range, other.domain_range):
                raise ValueError("The functions domains are different.")

            basisobj = self.basis.basis_of_product(other.basis)
            neval = max(constants.BASIS_MIN_FACTOR *
                        max(self.n_basis, other.n_basis) + 1,
                        constants.N_POINTS_COARSE_MESH)
            (left, right) = self.domain_range[0]
            evalarg = np.linspace(left, right, neval)

            first = self.copy(coefficients=(np.repeat(self.coefficients,
                                                      other.n_samples, axis=0)
                                            if (self.n_samples == 1 and
                                                other.n_samples > 1)
                                            else self.coefficients.copy()))
            second = other.copy(coefficients=(np.repeat(other.coefficients,
                                                        self.n_samples, axis=0)
                                              if (other.n_samples == 1 and
                                                  self.n_samples > 1)
                                              else other.coefficients.copy()))

            fdarray = first.evaluate(evalarg) * second.evaluate(evalarg)

            return FDataBasis.from_data(fdarray, evalarg, basisobj)

        if isinstance(other, int):
            other = [other for _ in range(self.n_samples)]

        coefs = np.transpose(np.atleast_2d(other))
        return self.copy(coefficients=self.coefficients * coefs)

    def _to_R(self):
        """Gives the code to build the object on fda package on R"""
        return ("fd(coef = " + self._array_to_R(self.coefficients, True) +
                ", basisobj = " + self.basis._to_R() + ")")

    def _array_to_R(self, coefficients, transpose=False):
        if len(coefficients.shape) == 1:
            coefficients = coefficients.reshape((1, coefficients.shape[0]))

        if len(coefficients.shape) > 2:
            return NotImplementedError

        if transpose is True:
            coefficients = np.transpose(coefficients)

        (rows, cols) = coefficients.shape
        retstring = "matrix(c("
        for j in range(cols):
            for i in range(rows):
                retstring = retstring + str(coefficients[i, j]) + ", "

        return (retstring[0:len(retstring) - 2] + "), nrow = " + str(rows) +
                ", ncol = " + str(cols) + ")")

    def __repr__(self):
        """Representation of FDataBasis object."""

        return (f"{self.__class__.__name__}("
                f"\nbasis={self.basis},"
                f"\ncoefficients={self.coefficients},"
                f"\ndataset_name={self.dataset_name},"
                f"\nargument_names={repr(self.argument_names)},"
                f"\ncoordinate_names={repr(self.coordinate_names)},"
                f"\nextrapolation={self.extrapolation})").replace(
                    '\n', '\n    ')

    def __str__(self):
        """Return str(self)."""

        return (f"{self.__class__.__name__}("
                f"\n_basis={self.basis},"
                f"\ncoefficients={self.coefficients})").replace('\n', '\n    ')

    def equals(self, other):
        """Equality of FDataBasis"""
        # TODO check all other params
        return (super().equals(other)
                and self.basis == other.basis
                and np.array_equal(self.coefficients, other.coefficients))

    def __eq__(self, other):
        """Elementwise equality of FDataBasis"""

        if type(self) != type(other) or self.dtype != other.dtype:
            raise TypeError("Types are not equal")

        if len(self) != len(other):
            raise ValueError(f"Different lengths: "
                             f"len(self)={len(self)} and "
                             f"len(other)={len(other)}")

        return np.all(self.coefficients == other.coefficients, axis=1)

    def concatenate(self, *others, as_coordinates=False):
        """Join samples from a similar FDataBasis object.

        Joins samples from another FDataBasis object if they have the same
        basis.

        Args:
            others (:class:`FDataBasis`): Objects to be concatenated.
            as_coordinates (boolean, optional):  If False concatenates as
                new samples, else, concatenates the other functions as
                new components of the image. Defaults to False.

        Returns:
            :class:`FDataBasis`: FDataBasis object with the samples from the
            original objects.

        Todo:
            By the moment, only unidimensional objects are supported in basis
            representation.
        """

        # TODO: Change to support multivariate functions
        #  in basis representation
        if as_coordinates:
            return NotImplemented

        for other in others:
            if other.basis != self.basis:
                raise ValueError("The objects should have the same basis.")

        data = [self.coefficients] + [other.coefficients for other in others]

        sample_names = [fd.sample_names for fd in [self, *others]]

        return self.copy(coefficients=np.concatenate(data, axis=0),
                         sample_names=sum(sample_names, ()))

    def compose(self, fd, *, eval_points=None, **kwargs):
        """Composition of functions.

        Performs the composition of functions. The basis is discretized to
        compute the composition.

        Args:
            fd (:class:`FData`): FData object to make the composition. Should
                have the same number of samples and image dimension equal to 1.
            eval_points (array_like): Points to perform the evaluation.
             kwargs: Named arguments to be passed to :func:`from_data`.
        """

        grid = self.to_grid().compose(fd, eval_points=eval_points)

        if fd.dim_domain == 1:
            basis = self.basis.rescale(fd.domain_range[0])
            composition = grid.to_basis(basis, **kwargs)
        else:
            #  Cant be convertered to basis due to the dimensions
            composition = grid

        return composition

    def __getitem__(self, key):
        """Return self[key]."""

        if isinstance(key, numbers.Integral):  # To accept also numpy ints
            key = int(key)
            if key < 0:
                key = range(len(self))[key]

            return self.copy(coefficients=self.coefficients[key:key + 1],
                             sample_names=self.sample_names[key:key + 1])
        else:
            return self.copy(coefficients=self.coefficients[key],
                             sample_names=np.array(self.sample_names)[key])

    def __add__(self, other):
        """Addition for FDataBasis object."""

        if isinstance(other, FDataBasis):
            if self.basis != other.basis:
                return NotImplemented
            else:
                basis, coefs = self.basis._add_same_basis(self.coefficients,
                                                          other.coefficients)

        else:
            try:
                basis, coefs = self.basis._add_constant(self.coefficients,
                                                        other)
            except TypeError:
                return NotImplemented

        return self._copy_op(other, basis=basis, coefficients=coefs)

    def __radd__(self, other):
        """Addition for FDataBasis object."""

        return self.__add__(other)

    def __sub__(self, other):
        """Subtraction for FDataBasis object."""
        if isinstance(other, FDataBasis):
            if self.basis != other.basis:
                return NotImplemented
            else:
                basis, coefs = self.basis._sub_same_basis(self.coefficients,
                                                          other.coefficients)
        else:
            try:
                basis, coefs = self.basis._sub_constant(self.coefficients,
                                                        other)
            except TypeError:
                return NotImplemented

        return self._copy_op(other, basis=basis, coefficients=coefs)

    def __rsub__(self, other):
        """Right subtraction for FDataBasis object."""
        return (self * -1).__add__(other)

    def __mul__(self, other):
        """Multiplication for FDataBasis object."""
        if isinstance(other, FDataBasis):
            return NotImplemented

        try:
            basis, coefs = self.basis._mul_constant(self.coefficients, other)
        except TypeError:
            return NotImplemented

        return self._copy_op(other, basis=basis, coefficients=coefs)

    def __rmul__(self, other):
        """Multiplication for FDataBasis object."""
        return self.__mul__(other)

    def __truediv__(self, other):
        """Division for FDataBasis object."""

        other = np.array(other)

        try:
            other = 1 / other
        except TypeError:
            return NotImplemented

        return self * other

    def __rtruediv__(self, other):
        """Right division for FDataBasis object."""

        return NotImplemented

    #####################################################################
    # Pandas ExtensionArray methods
    #####################################################################
    @property
    def dtype(self):
        """The dtype for this extension array, FDataGridDType"""
        return FDataBasisDType(basis=self.basis)

    @property
    def nbytes(self) -> int:
        """
        The number of bytes needed to store this object in memory.
        """
        return self.coefficients.nbytes()

    def isna(self):
        """
        A 1-D array indicating if each value is missing.

        Returns:
            na_values (np.ndarray): Positions of NA.
        """
        return np.all(np.isnan(self.coefficients), axis=1)


class FDataBasisDType(pandas.api.extensions.ExtensionDtype):
    """
    DType corresponding to FDataBasis in Pandas
    """
    kind = 'O'
    type = FDataBasis
    name = 'FDataBasis'
    na_value = pandas.NA

    _metadata = ("basis")

    def __init__(self, basis) -> None:
        self.basis = basis

    @classmethod
    def construct_array_type(cls) -> type:
        return FDataBasis

    def _na_repr(self) -> FDataBasis:
        return FDataBasis(
            basis=self.basis,
            coefficients=((np.NaN,) * self.basis.n_basis,))

    def __eq__(self, other: Any) -> bool:
        """
        Rules for equality (similar to categorical):
        1) Any FData is equal to the string 'category'
        2) Any FData is equal to itself
        3) Otherwise, they are equal if the arguments are equal.
        6) Any other comparison returns False
        """
        if isinstance(other, str):
            return other == self.name
        elif other is self:
            return True
        else:
            return (isinstance(other, FDataBasisDType)
                    and self.basis == other.basis)

    def __hash__(self) -> int:
        return hash(self.basis)
