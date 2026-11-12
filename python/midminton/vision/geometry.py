"""Court-plane geometry. An airborne shuttle must never be treated as a landing."""
from math import isfinite


class Court:
    def __init__(self, corners):
        if len(corners) != 4 or any(len(p) != 2 for p in corners):
            raise ValueError("Court needs four ordered corners")
        if any(not isfinite(float(v)) or not 0 <= v <= 1 for p in corners for v in p):
            raise ValueError("Court coordinates must be normalized")
        matrix = []
        for (x, y), (u, v) in zip(corners, [(0, 0), (1, 0), (1, 1), (0, 1)]):
            matrix.extend([[x, y, 1, 0, 0, 0, -u*x, -u*y, u],
                           [0, 0, 0, x, y, 1, -v*x, -v*y, v]])
        for column in range(8):
            pivot = max(range(column, 8), key=lambda row: abs(matrix[row][column]))
            matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
            scale = matrix[column][column]
            if abs(scale) < 1e-9:
                raise ValueError("Court corners are degenerate; mark them again")
            matrix[column] = [n/scale for n in matrix[column]]
            for row in range(8):
                if row != column:
                    scale = matrix[row][column]
                    matrix[row] = [a-scale*b for a, b in zip(matrix[row], matrix[column])]
        self.h = [row[-1] for row in matrix]
        turns = []
        for i in range(4):
            a, b, c = corners[i], corners[(i+1) % 4], corners[(i+2) % 4]
            turns.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
        if not (all(t > 1e-5 for t in turns) or all(t < -1e-5 for t in turns)):
            raise ValueError("Court corners must form a convex, ordered quadrilateral")

    def project(self, point):
        x, y = point
        a, b, c, d, e, f, g, h = self.h
        denominator = g*x+h*y+1
        if abs(denominator) < 1e-8:
            return None
        return [(a*x+b*y+c)/denominator, (d*x+e*y+f)/denominator]

    def foot(self, box):
        return self.project([(box[0]+box[2])/2, box[3]])

    def contains(self, point, margin=0.12):
        mapped = self.project(point)
        return mapped is not None and all(-margin <= v <= 1+margin for v in mapped)
