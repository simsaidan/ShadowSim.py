"""Local operators on chosen sites."""

import numpy as np

from shadowsim.core.operator import Operator, _Matrix


def _matrix_on_increasing_sites(matrix: _Matrix, sites: list[int], local_dim: int) -> _Matrix:
    """Return ``matrix`` with tensor factors ordered by increasing site index.

    ``sites[i]`` is tensor factor ``i`` of ``matrix``, and factor 0 is the most
    significant factor. The first factor of the result corresponds to
    ``min(sites)``. A sorted ``sites`` list is returned unchanged.
    """
    ordered = sorted(sites)
    if sites == ordered:
        return matrix
    factor_of_site = {site: index for index, site in enumerate(sites)}
    permutation = [factor_of_site[site] for site in ordered]
    width = len(sites)
    reshaped = np.asarray(matrix).reshape((local_dim,) * (2 * width))
    axes = permutation + [index + width for index in permutation]
    permuted = np.transpose(reshaped, axes).reshape(matrix.shape)
    return np.ascontiguousarray(permuted)


def _embed_with_identity_gaps(matrix: _Matrix, sites: list[int], total_sites: int, local_dim: int) -> _Matrix:
    """Embed ``matrix`` on ``sites`` with identity on every other site.

    Tensor factors follow ``sites`` and are reordered to increasing site index
    first. Factor 0 is the most significant factor. The result uses that order
    on ``0 .. total_sites - 1``, so a gap such as ``[0, 2]`` leaves identity on
    site 1.
    """
    ordered_sites = sorted(sites)
    ordered = _matrix_on_increasing_sites(matrix, sites, local_dim)
    present = set(ordered_sites)
    missing = [site for site in range(total_sites) if site not in present]
    embedded = ordered
    eye = np.eye(local_dim, dtype=np.asarray(ordered).dtype)
    for _ in missing:
        embedded = np.kron(embedded, eye)
    current = ordered_sites + missing
    inverse = [current.index(site) for site in range(total_sites)]
    factored = np.asarray(embedded).reshape((local_dim,) * (2 * total_sites))
    axes = inverse + [total_sites + index for index in inverse]
    permuted = np.transpose(factored, axes)
    full_dim = local_dim**total_sites
    return np.ascontiguousarray(permuted.reshape((full_dim, full_dim)))


class LocalOperator(Operator):
    """Represent an operator that acts non-trivially on given sites.

    The operator acts on the given ``sites`` of a tensor-product space.
    ``sites[i]`` is tensor factor ``i`` of ``matrix``, and factor 0 is the most
    significant factor, in the same order as ``tensor``. Site order names the
    factors, so ``[0, 1]`` and ``[1, 0]`` are different operators. Sites may
    skip indexes; embedding puts identity on every skipped site.
    """

    def __init__(self, matrix: _Matrix, sites: list[int], local_dim: int = 2) -> None:
        """Initialize a LocalOperator acting non-trivially on the given sites.

        Parameter matrix: The matrix representation of the operator.
        Precondition: matrix is a numpy array.

        Parameter sites: The sites on which the operator acts non-trivially, in
            tensor-factor order. ``sites[0]`` is the first factor of ``matrix``.
        Precondition: sites is a non-empty list of distinct integers.

        Parameter local_dim: The local dimension of the operator.
        Precondition: local_dim is a positive integer.
        """
        if not isinstance(matrix, np.ndarray):
            raise TypeError(f"matrix must be a numpy array; got {type(matrix)!r}")
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError(f"matrix must be a square 2D array; got shape {matrix.shape}")
        if not isinstance(sites, list):
            raise TypeError(f"sites must be a list; got {type(sites)!r}")
        if not all(isinstance(site, int) for site in sites):
            raise TypeError(f"all sites must be integers; got {sites}")
        if len(set(sites)) != len(sites):
            raise ValueError(f"all sites must be unique; got {sites}")
        if len(sites) < 1:
            raise ValueError(f"there must be at least one site; got {sites}")
        if not isinstance(local_dim, int):
            raise TypeError(f"local_dim must be an integer; got {type(local_dim)!r}")
        if local_dim <= 0:
            raise ValueError(f"local_dim must be a positive integer; got {local_dim}")

        expected_dim = local_dim ** len(sites)
        if matrix.shape[0] != expected_dim:
            raise ValueError(
                "invalid number of sites for the given matrix: "
                f"got len(sites)={len(sites)} and local_dim={local_dim}, "
                f"expected matrix dimension {expected_dim}x{expected_dim}, "
                f"but got {matrix.shape[0]}x{matrix.shape[1]}"
            )

        super().__init__(matrix)
        self.sites = sites
        self.local_dim = local_dim

    def get_sites(self) -> list[int]:
        """Return the sites on which the local operator acts non-trivially."""
        return self.sites

    def get_local_dim(self) -> int:
        """Return the local dimension of the local operator."""
        return self.local_dim

    def get_matrix(self) -> _Matrix:
        """Return the matrix representation of the local operator."""
        return self.matrix

    def to_operator(self) -> Operator:
        """Return an Operator representing the local operator."""
        return Operator(self.matrix)

    def to_full_operator(self, total_sites: int) -> Operator:
        """Embed this local operator into a full system of ``total_sites``.

        The operator acts on ``self.sites`` and identity acts on every other
        site, including sites that sit in a gap. ``sites[0]`` is the first
        tensor factor of the stored matrix. A site list that is not in
        increasing order is permuted into that order before the identities are
        inserted.

        Parameter total_sites: The total number of sites in the full system.
        Precondition: total_sites is a positive integer.
        """
        if not isinstance(total_sites, int):
            raise TypeError(f"total_sites must be an integer; got {type(total_sites)!r}")
        if total_sites < 1:
            raise ValueError(f"total_sites must be positive; got {total_sites}")

        lo, hi = min(self.sites), max(self.sites)
        if lo < 0:
            raise ValueError(f"site indices must be non-negative; got {self.sites}")
        if hi >= total_sites:
            raise ValueError(f"total_sites={total_sites} is too small for local sites {self.sites}")

        full_matrix = _embed_with_identity_gaps(self.matrix, self.sites, total_sites, self.local_dim)
        return Operator(full_matrix)

    def __str__(self) -> str:
        """Return a string representation of the local operator."""
        return f"LocalOperator(sites={self.sites}, local_dim={self.local_dim}, shape={self.matrix.shape})"

    def __repr__(self) -> str:
        """Return a string representation of the local operator."""
        return f"LocalOperator(matrix={self.matrix!r}, sites={self.sites!r}, local_dim={self.local_dim})"
