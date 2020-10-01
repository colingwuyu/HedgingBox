from scipy import interpolate
import numpy as np
import tensorflow as tf
from typing import Union, List
from hb.utils.consts import np_dtype

class ImpliedVolSurface(object):
    __slots__ = ["_implied_vol_surf", "_scalar", "_maturities", "_strikes"]

    def __init__(self,
                 maturities,
                 strikes,
                 implied_vol_matrix,
                 backup_vol):
        if (maturities.shape[0] == 1) and (strikes.shape[0] == 1):
            self._implied_vol_surf = implied_vol_matrix[0][0]
            self._maturities = maturities
            self._strikes = strikes
            self._scalar = True
        else:
            if maturities.shape[0] == 1:
                maturities = tf.concat([maturities, maturities*1.1],-1)
                implied_vol_matrix = tf.concat([implied_vol_matrix, implied_vol_matrix],-1)
            elif strikes.shape[0] == 1:
                strikes = tf.concat([strikes, strikes*1.1],-1)
                implied_vol_matrix = tf.concat([implied_vol_matrix, implied_vol_matrix],-1)
            total_var_matrix = np.transpose(implied_vol_matrix.numpy()**2)*maturities
            total_var_matrix = total_var_matrix.numpy()
            self._strikes = strikes.numpy()
            self._maturities = maturities.numpy()
            for m_i in range(total_var_matrix.shape[1]):
                nans = np.isnan(total_var_matrix[:,m_i])
                if nans.all():
                    total_var_matrix[nans.nonzero()[0],m_i] = backup_vol
                elif self._strikes[~nans].shape[0] > 1:
                    fillna = interpolate.interp1d(self._strikes[~nans],total_var_matrix[~nans,m_i],bounds_error=False,
                                                  fill_value=(total_var_matrix[~nans,m_i][0],total_var_matrix[~nans,m_i][-1]))
                    total_var_matrix[nans.nonzero()[0],m_i] = fillna(self._strikes[nans])
                else:
                    total_var_matrix[nans.nonzero()[0],m_i] = total_var_matrix[~nans,m_i][0]
            self._implied_vol_surf = interpolate.interp2d(self._maturities,self._strikes,total_var_matrix)
            self._scalar = False

    def get_black_vol(self, t: float, k: float):
        if self._scalar:
            return self._implied_vol_surf
        else:
            if t < self._maturities[0]:
                t = self._maturities[0]
            elif t > self._maturities[-1]:
                t = self._maturities[-1]
            black_vol = (self._implied_vol_surf(t, k)[0]/t)**0.5
            return tf.constant(black_vol, dtype=np_dtype)

    def get_black_variance(self, t, k):
        if self._scalar:
            return self._implied_vol_surf
        else:
            if t < self._maturities[0]:
                t = self._maturities[0]
            elif t > self._maturities[-1]:
                t = self._maturities[-1]
            black_variance = self._implied_vol_surf(t, k)[0]/t
            return tf.constant(black_variance, dtype=np_dtype)