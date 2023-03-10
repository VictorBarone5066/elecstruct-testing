#Reorganized to be more cache friendly (array stored w/ fastest index begin z, then y, then x as the slowest)

from numpy import empty, linspace, sin, cos, pi, transpose, exp, array
from scipy.fft import fft, ifft, fftn, ifftn

def func(x, y, z):
    return sin(50.0*2.0*pi*x*z) + 0.5*sin(80.0*2.0*pi*y) + 10.47*cos(24.0*2.0*pi*x*y*z)*1.j

PX, PY, PZ = 5, 3, 6
NX, NY, NZ = 2**PX, 2**PY, 2**PZ ##12 = 4096
LOX, HIX, LOY, HIY, LOZ, HIZ = -1.23, 3.54, 3.47, 6.21, -0.56, 8.80
BASE = empty(shape=(NX, NY, NZ), dtype=complex).tolist()
for nx, x in enumerate(linspace(LOX, HIX, NX)):
    for ny, y in enumerate(linspace(LOY, HIY, NY)):
        for nz, z in enumerate(linspace(LOZ, HIZ, NZ)):
            BASE[nx][ny][nz] = func(x, y, z)

#lookup tables, needs to describe (0 <= angle < pi/2)
#we send in the argument (0 <= 2*arg/pi < 1.0) and are returned the value sin(arg) or cos(arg)
##init
TABLE_LEN = 256
luts = [None for i in range(0, TABLE_LEN)] ##print these out to float prec, declare static arrays in c
lutc = [None for i in range(0, TABLE_LEN)]
##fill
for i in range(0, TABLE_LEN):
    luts[i] = sin(pi*i/2./(TABLE_LEN-1)) ##using table_len-1 removes the need for an oob check, along with below
    lutc[i] = cos(pi*i/2./(TABLE_LEN-1)) ##comment on using TABLE_LEN-1
#setup for lin interp
def intp(argoverpi):
    i1 = int(argoverpi)
    i2 = i1 + 1

    r1s = luts[i1]
    si = r1s + (luts[i2]-r1s)*(argoverpi-float(i1))

    r1c = lutc[i1]
    co = r1c + (lutc[i2]-r1c)*(argoverpi-float(i1))
    return si, co



#from matplotlib import pyplot as plt
#x = list(linspace(0, pi/2-1e-8, 1000))
#ys, yc = [], []
#for i in range(0, 1000):
#    arg = 2*x[i]/pi*(TABLE_LEN-1) ##calling like this removes the need for an oob check.  see 'fill'
#    si, co = intp(arg)
#    ys.append(si)
#    yc.append(co)

#plt.plot(x, [sin(x_) for x_ in x], 'k')
#plt.plot(x, [cos(x_) for x_ in x], 'k--')
#plt.plot(x, ys, 'b')
#plt.plot(x, yc, 'b--')

#plt.plot(x, array(ys) - array([sin(x_) for x_ in x]), 'k')
#plt.plot(x, array(yc) - array([cos(x_) for x_ in x]), 'k--')

#plt.show()

#exit(2)

#Algos for bit reversal---------------------------------------------------------------------------------------
def revbinupdate(a, b):
    ## a ^= b means a = a ^ b (^ is XOR)
    ## used to be 'revbinupdate(a, b); while(!(a ^= b) & b); {b >>= 1}; return a;'
    a = a^b
    while(not((a) & b)):
        b >>= 1
        a = a^b
    return a

#Permutation of arr's indices (arr is length n) that undo the bit-reversal that the dif/dit in-place fft algos
#do.  also needed is the half length of the array, nh = n >> 1
def _revbinpermute(arr, n, nh):
    if(n <= 2):
        return arr

    i = 0
    j = 1

    while(j < nh):
        #odd j portion
        i += nh
        arr[j], arr[i] = arr[i], arr[j]
        j += 1

        #even j portion
        i = revbinupdate(i, nh)
        if(i > j):
            arr[j], arr[i] = arr[i], arr[j]
            arr[n-j-1], arr[n-i-1] = arr[n-i-1], arr[n-j-1]
        j += 1

    return arr

#FFT Algos----------------------------------------------------------------------------------------------------
#1D DIT FFT algo with no bit reversal section
#this one is arranged for good memory access, but is most efficient when a trig table is used due to the
#increased number of calls to complex exp
#Needs the array to edit, the log_2(its size), its size, and x, the value in exp(ixj) (may be neg for ifft)
#Note1: permute is done BEFORE the dit algo ... NOTE2: x is often just isign * pi

#Cos/Sin tables for recurrence.  Declare these static, maybe extern, and hard code them in
L2M_MAX = 32 ##all fft grid sizes must be <= 2^(L2M_MAX)
CT = [None for i in range(0, L2M_MAX)] ##covers all the way up to 2^32
ST = [None for i in range(0, L2M_MAX)] ##might reasonably only go up to 2^16 or so ...

for i in range(2, L2M_MAX):
    d = (1 << i) >> 1
    CT[i] = cos(pi/float(d))
    ST[i] = sin(pi/float(d))

from numpy import round
def _fftbasedit(arr, l2n, n, isign):

    ##explicitly do the trivial 1+0i multiplications
    for i in range(0, n, 2):
        u = arr[i] + arr[i+1]
        v = arr[i] - arr[i+1]
        arr[i]   = u
        arr[i+1] = v
    ##do the rest of the transform
    for ldm in range(2, l2n+1):
        m = 1<<ldm
        mh = m>>1
        phi = pi*isign / float(mh)

        for i in range(0, n, m):
            ###again, explicit 1+0i multiplications
            ijmh = i + mh
            u = arr[i] + arr[ijmh]
            v = arr[i] - arr[ijmh]
            arr[i]    = u
            arr[ijmh] = v

            ###-----trig recurr-----
            ##see https://en.wikipedia.org/wiki/Trigonometric_tables if we need less prec loss
            #print(ldm, phi)
            #wr = cos(phi)
            #wi = sin(phi)
            wr = CT[ldm]
            wi = isign*ST[ldm]
            cn = wr*1 - wi*0
            sn = wi*1 + wr*0
            ###---------------------
            for j in range(1, mh):
                ij = i + j
                ijmh = ij + mh

                e1 = exp(phi*float(j)*1.0j)
                e2 = cn + 1.0j*sn

                #print(i, j, round(e1, 3), round(e2, 3))

                u = arr[ij]
                v = arr[ijmh] * e2
                arr[ij]   = u + v
                arr[ijmh] = u - v

                ##update trig rec
                cnt = cn
                cn = wr*cn - wi*sn
                sn = wi*cnt + wr*sn
    return arr

#1D DIF FFT algo with no bit reversal section
#this one is arranged for good memory access, but is most efficient when a trig table is used due to the
#increased number of calls to complex exp
#Needs the array to edit, the log_2(its size), its size, and x, the value in exp(ixj) (may be neg for ifft)
#Note1: permute is done AFTER the dif algo ... NOTE2: x is often just isign * pi
def _fftbasedif(arr, l2n, n, isign):
    ##do most of the transform
    for ldm in range(l2n, 1, -1): ##ldm=l2n; ldm >= 2; --ldm
        m = 1<<ldm
        mh = m>>1
        phi = pi*isign / float(mh)

        for i in range(0, n, m):
            for j in range(0, mh):
                ij = i + j
                ijmh = ij + mh

                u = arr[ij]
                v = arr[ijmh]
                arr[ij]   =  u + v
                arr[ijmh] = (u - v) * exp(phi*float(j)*1.0j) ##call to trig table with index j
    ##explicitly do the trivial 1+0i multiplications
    for i in range(0, n, 2):
        tmpip0 = arr[i] + arr[i+1]
        tmpip1 = arr[i] - arr[i+1]
        arr[i]   = tmpip0
        arr[i+1] = tmpip1

    return arr


#Stuff for moving between 3d and 1d representations
##we don't actually need lx here
def _acc3(i, j, k, lx, ly, lz):
    #return i*(ly*lz) + j*(lz) + k
    return (i*ly + j)*lz + k

def to1d(grid, lx, ly, lz):
    ret = empty(shape=lx*ly*lz, dtype=complex)
    for i in range(0, lx):
        for j in range(0, ly):
            for k in range(0, lz):
                ret[_acc3(i, j, k, lx, ly, lz)] = grid[i][j][k]
    return ret

def to3d(arr, lx, ly, lz):
    ret = empty(shape=(lx,ly,lz), dtype=complex)
    for i in range(0, lx):
        for j in range(0, ly):
            for k in range(0, lz):
                ret[i][j][k] = arr[_acc3(i, j, k, lx, ly, lz)]
    return ret


"""
I haven't bothered to change the ordering of these loops yet, so here they will lie forever


def fft3dit(arr, buff, pows, sizes, isign):
    ##permute---------------------------------------------------------
    for i in range(0, sizes[0]):
        for j in range(0, sizes[1]):
            for k in range(0, sizes[2]):
                buff[k] = arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])]
            buff[0:sizes[2]] = _revbinpermute(arr=buff[0:sizes[2]], n=sizes[2], nh=sizes[2]//2)
            for k in range(0, sizes[2]):
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = buff[k]
    for i in range(0, sizes[0]):
        for k in range(0, sizes[2]):
            for j in range(0, sizes[1]):
                buff[j] = arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])]
            buff[0:sizes[1]] = _revbinpermute(arr=buff[0:sizes[1]], n=sizes[1], nh=sizes[1]//2)
            for j in range(0, sizes[1]):
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = buff[j]
    for j in range(0, sizes[1]): ##we actually don't need a buffer for this one
        for k in range(0, sizes[2]):
            lo = _acc3(0, j, k,        sizes[0], sizes[1], sizes[2])
            hi = _acc3(sizes[0], j, k, sizes[0], sizes[1], sizes[2])
            arr[lo:hi] = _revbinpermute(arr=arr[lo:hi], n=sizes[0], nh=sizes[0]//2)

    ##fft------------------------------------------------------------
    for i in range(0, sizes[0]):
        for j in range(0, sizes[1]):
            for k in range(0, sizes[2]):
                buff[k] = arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])]
            buff[0:sizes[2]] = _fftbasedit(arr=buff[0:sizes[2]], l2n=pows[2], n=sizes[2], x=isign*pi)
            for k in range(0, sizes[2]):
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = buff[k]
    for i in range(0, sizes[0]):
        for k in range(0, sizes[2]):
            for j in range(0, sizes[1]):
                buff[j] = arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])]
            buff[0:sizes[1]] = _fftbasedit(arr=buff[0:sizes[1]], l2n=pows[1], n=sizes[1], x=isign*pi)
            for j in range(0, sizes[1]):
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = buff[j]
    for j in range(0, sizes[1]): ##we actually don't need a buffer for this one
        for k in range(0, sizes[2]):
            lo = _acc3(0, j, k,        sizes[0], sizes[1], sizes[2])
            hi = _acc3(sizes[0], j, k, sizes[0], sizes[1], sizes[2])
            arr[lo:hi] = _fftbasedit(arr=arr[lo:hi], l2n=pows[0], n=sizes[0], x=isign*pi)

    return arr


def fft3dif(arr, buff, pows, sizes, isign):
    ##fft------------------------------------------------------------
    for i in range(0, sizes[0]):
        for j in range(0, sizes[1]):
            for k in range(0, sizes[2]):
                buff[k] = arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])]
            buff[0:sizes[2]] = _fftbasedif(arr=buff[0:sizes[2]], l2n=pows[2], n=sizes[2], x=isign*pi)
            for k in range(0, sizes[2]):
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = buff[k]
    for i in range(0, sizes[0]):
        for k in range(0, sizes[2]):
            for j in range(0, sizes[1]):
                buff[j] = arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])]
            buff[0:sizes[1]] = _fftbasedif(arr=buff[0:sizes[1]], l2n=pows[1], n=sizes[1], x=isign*pi)
            for j in range(0, sizes[1]):
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = buff[j]
    for j in range(0, sizes[1]): ##we actually don't need a buffer for this one
        for k in range(0, sizes[2]):
            lo = _acc3(0, j, k,        sizes[0], sizes[1], sizes[2])
            hi = _acc3(sizes[0], j, k, sizes[0], sizes[1], sizes[2])
            arr[lo:hi] = _fftbasedif(arr=arr[lo:hi], l2n=pows[0], n=sizes[0], x=isign*pi)

    ##permute---------------------------------------------------------
    for i in range(0, sizes[0]):
        for j in range(0, sizes[1]):
            for k in range(0, sizes[2]):
                buff[k] = arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])]
            buff[0:sizes[2]] = _revbinpermute(arr=buff[0:sizes[2]], n=sizes[2], nh=sizes[2]//2)
            for k in range(0, sizes[2]):
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = buff[k]
    for i in range(0, sizes[0]):
        for k in range(0, sizes[2]):
            for j in range(0, sizes[1]):
                buff[j] = arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])]
            buff[0:sizes[1]] = _revbinpermute(arr=buff[0:sizes[1]], n=sizes[1], nh=sizes[1]//2)
            for j in range(0, sizes[1]):
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = buff[j]
    for j in range(0, sizes[1]): ##we actually don't need a buffer for this one
        for k in range(0, sizes[2]):
            lo = _acc3(0, j, k,        sizes[0], sizes[1], sizes[2])
            hi = _acc3(sizes[0], j, k, sizes[0], sizes[1], sizes[2])
            arr[lo:hi] = _revbinpermute(arr=arr[lo:hi], n=sizes[0], nh=sizes[0]//2)

    return arr
"""




#This is a bit better than the above one at the cost of twice (!) the memory
#Yes, I know that this is stupidly inefficient (better to combine the bit reversals inside of the ffts),
#but this is just setup or ignoring the bit reversals altogether
def fft3dif_(arr, pows, sizes, isign):
    tmp = empty(shape=sizes[0]*sizes[1]*sizes[2], dtype=complex)

    ##fft------------------------------------------------------------
    for i in range(0, sizes[0]): ##ijk loop
        for j in range(0, sizes[1]):
            lo = _acc3(i, j, 0, sizes[0], sizes[1], sizes[2])
            arr[lo:lo+sizes[2]] = _fftbasedif(arr=arr[lo:lo+sizes[2]], l2n=pows[2], n=sizes[2], isign=isign)
            for k in range(0, sizes[2]): ##permute ijk -> jki
                tmp[_acc3(j, k, i, sizes[1], sizes[2], sizes[0])] = arr[lo + k]
    for j in range(0, sizes[1]): ##jki loop
        for k in range(0, sizes[2]):
            lo = _acc3(j, k, 0, sizes[1], sizes[2], sizes[0])
            tmp[lo:lo+sizes[0]] = _fftbasedif(arr=tmp[lo:lo+sizes[0]], l2n=pows[0], n=sizes[0], isign=isign)
            for i in range(0, sizes[0]): ##permute jki -> kij
                arr[_acc3(k, i, j, sizes[2], sizes[0], sizes[1])] = tmp[lo + i]
    for k in range(0, sizes[2]): ##kij loop
        for i in range(0, sizes[0]):
            lo = _acc3(k, i, 0, sizes[2], sizes[0], sizes[1])
            arr[lo:lo+sizes[1]] = _fftbasedif(arr=arr[lo:lo+sizes[1]], l2n=pows[1], n=sizes[1], isign=isign)
            for j in range(0, sizes[1]): ##permute kij -> ijk
                tmp[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = arr[lo + j]

    ##permute---------------------------------------------------------
    for i in range(0, sizes[0]): ##ijk loop
        for j in range(0, sizes[1]):
            lo = _acc3(i, j, 0, sizes[0], sizes[1], sizes[2])
            tmp[lo:lo+sizes[2]] = _revbinpermute(arr=tmp[lo:lo+sizes[2]], n=sizes[2], nh=sizes[2]//2)
            for k in range(0, sizes[2]): ##permute ijk -> jki
                arr[_acc3(j, k, i, sizes[1], sizes[2], sizes[0])] = tmp[lo + k]
    for j in range(0, sizes[1]): ##jki loop
        for k in range(0, sizes[2]):
            lo = _acc3(j, k, 0, sizes[1], sizes[2], sizes[0])
            arr[lo:lo+sizes[0]] = _revbinpermute(arr=arr[lo:lo+sizes[0]], n=sizes[0], nh=sizes[0]//2)
            for i in range(0, sizes[0]): ##permute jki -> kij
                tmp[_acc3(k, i, j, sizes[2], sizes[0], sizes[1])] = arr[lo + i]
    for k in range(0, sizes[2]): ##kij loop
        for i in range(0, sizes[0]):
            lo = _acc3(k, i, 0, sizes[2], sizes[0], sizes[1])
            tmp[lo:lo + sizes[1]] = _revbinpermute(arr=tmp[lo:lo+sizes[1]], n=sizes[1], nh=sizes[1]//2)
            for j in range(0, sizes[1]): ##permute kij -> ijk
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = tmp[lo + j]

    return arr




#This is a bit better than the above one at the cost of twice (!) the memory
def fft3dit_(arr, pows, sizes, isign):
    tmp = empty(shape=sizes[0]*sizes[1]*sizes[2], dtype=complex)

    ##permute---------------------------------------------------------
    for i in range(0, sizes[0]): ##ijk loop
        for j in range(0, sizes[1]):
            lo = _acc3(i, j, 0, sizes[0], sizes[1], sizes[2])
            arr[lo:lo+sizes[2]] = _revbinpermute(arr=arr[lo:lo+sizes[2]], n=sizes[2], nh=sizes[2]//2)
            for k in range(0, sizes[2]): ##permute ijk -> jki
                tmp[_acc3(j, k, i, sizes[1], sizes[2], sizes[0])] = arr[lo + k]
    for j in range(0, sizes[1]): ##jki loop
        for k in range(0, sizes[2]):
            lo = _acc3(j, k, 0, sizes[1], sizes[2], sizes[0])
            tmp[lo:lo+sizes[0]] = _revbinpermute(arr=tmp[lo:lo+sizes[0]], n=sizes[0], nh=sizes[0]//2)
            for i in range(0, sizes[0]): ##permute jki -> kij
                arr[_acc3(k, i, j, sizes[2], sizes[0], sizes[1])] = tmp[lo + i]
    for k in range(0, sizes[2]): ##kij loop
        for i in range(0, sizes[0]):
            lo = _acc3(k, i, 0, sizes[2], sizes[0], sizes[1])
            arr[lo:lo + sizes[1]] = _revbinpermute(arr=arr[lo:lo+sizes[1]], n=sizes[1], nh=sizes[1]//2)
            for j in range(0, sizes[1]): ##permute kij -> ijk
                tmp[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = arr[lo + j]

    ##fft------------------------------------------------------------
    for i in range(0, sizes[0]): ##ijk loop
        for j in range(0, sizes[1]):
            lo = _acc3(i, j, 0, sizes[0], sizes[1], sizes[2])
            tmp[lo:lo+sizes[2]] = _fftbasedit(arr=tmp[lo:lo+sizes[2]], l2n=pows[2], n=sizes[2], isign=isign)
            for k in range(0, sizes[2]): ##permute ijk -> jki
                arr[_acc3(j, k, i, sizes[1], sizes[2], sizes[0])] = tmp[lo + k]
    for j in range(0, sizes[1]): ##jki loop
        for k in range(0, sizes[2]):
            lo = _acc3(j, k, 0, sizes[1], sizes[2], sizes[0])
            arr[lo:lo+sizes[0]] = _fftbasedit(arr=arr[lo:lo+sizes[0]], l2n=pows[0], n=sizes[0], isign=isign)
            for i in range(0, sizes[0]): ##permute jki -> kij
                tmp[_acc3(k, i, j, sizes[2], sizes[0], sizes[1])] = arr[lo + i]
    for k in range(0, sizes[2]): ##kij loop
        for i in range(0, sizes[0]):
            lo = _acc3(k, i, 0, sizes[2], sizes[0], sizes[1])
            tmp[lo:lo+sizes[1]] = _fftbasedit(arr=tmp[lo:lo+sizes[1]], l2n=pows[1], n=sizes[1], isign=isign)
            for j in range(0, sizes[1]): ##permute kij -> ijk
                arr[_acc3(i, j, k, sizes[0], sizes[1], sizes[2])] = tmp[lo + j]

    return arr



#Testing------------------------------------------------------------------------------------------------------
from copy import deepcopy

#The FFT Tests--------------------------------------------------------
res1 = fftn(x=deepcopy(BASE), s=(NX, NY, NZ))
buffer = empty(shape=max(NX, NY, NZ), dtype=complex)
BASE = to1d(grid=deepcopy(BASE), lx=NX, ly=NY, lz=NZ)
if(0):
    res2 = fft3dit(arr=deepcopy(BASE), buff=buffer, pows=[PX, PY, PZ], sizes=[NX, NY, NZ], isign=-1)
    res2 = to3d(arr=deepcopy(res2), lx=NX, ly=NY, lz=NZ)
    res3 = fft3dif(arr=deepcopy(BASE), buff=buffer, pows=[PX, PY, PZ], sizes=[NX, NY, NZ], isign=-1)
    res3 = to3d(arr=deepcopy(res3), lx=NX, ly=NY, lz=NZ)
    from numpy import max
    print(max(res1 - res2))
    print(max(res1 - res3))
    print(max(res2 - res3))
if(1):
    res2 = fft3dit_(arr=deepcopy(BASE), pows=[PX, PY, PZ], sizes=[NX, NY, NZ], isign=-1)
    res2 = to3d(arr=deepcopy(res2), lx=NX, ly=NY, lz=NZ)
    res3 = fft3dif_(arr=deepcopy(BASE), pows=[PX, PY, PZ], sizes=[NX, NY, NZ], isign=-1)
    res3 = to3d(arr=deepcopy(res3), lx=NX, ly=NY, lz=NZ)
    from numpy import max
    print(max(res1 - res2))
    print(max(res1 - res3))
    print(max(res2 - res3))
