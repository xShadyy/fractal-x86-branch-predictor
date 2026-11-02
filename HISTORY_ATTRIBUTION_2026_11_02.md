# Commit attribution correction and evidence provenance

On 2 November 2026, 12 commits had their author and committer identity corrected
from a mistakenly configured tool identity to
`Tymoteusz Netter <131590030+xShadyy@users.noreply.github.com>`. This rewrote the commit IDs
of those 12 commits and 20 descendants. For every old/new pair, the Git tree
is identical: source files, code, archived data, commit message and original
author/committer timestamps were not changed. The public branch was verified
at `b714b61ea11cdb54a610557dcd7c138b06937723` before correction;
seven later commits in the working series were also mapped for future import.

Original physical evidence ZIPs and reports record the Git HEAD observed at
build time. **Those historical fields must not be edited**. Use the table
below to locate the equivalent code tree in corrected history. Exact old
commit objects are preserved in a separate original-history Git bundle,
`fractal-x86-pre-attribution-history-20261102.bundle`, SHA-256
`6769170ee55d8704c802146f92572aebcdb2f425f07e8e03c691ddaff2a27197`.
Do not push an old-history backup branch to GitHub or merge it back into
`main`. The original archive bytes and their SHA-256 hashes remain unchanged.

| Recorded commit | Equivalent corrected commit | Identical tree |
| --- | --- | --- |
| `a06b1d6ae35c02381bca1822ba44205ab6b6ab80` | `f789d30e8fc1e088797b03786bbf425b1b4c0d27` | `7b5a13c4513cfe0a9aaabb55f5014b2f2b122f9c` |
| `c1f5299f734d7d9a148dcae1dda2d4cd8941e55f` | `f6b9d0aea4eb6704fe4a2a1a5e0c82f68a44d390` | `1c4bc261d135a4ae7a27f0fe47583848a18a032a` |
| `84f6182049b0e1815f82a2622f3f26423f665692` | `ac9085a3a4a8f2700e61fb40ee549bc935412b75` | `e710a7fdc4b9f5f947df5a476abc4a3e30f16c4b` |
| `ec7f6269136019270a91e82c2665b7aa0aca1286` | `6adb59b433ebdb1bd986227fcaf19d77a03211c9` | `d980ad2c7c1867cbb293e1994895059e6b245e84` |
| `57be586e93721ba42705a50c6cffdd3ad6e315c9` | `ef9f7a766a661db3e3d56851fce78174ef0b99c7` | `2f5bbd5378add9548824b451311090d364dac6e1` |
| `ed212ed23bbe109d6a3e1a5ef75afed1a9febb9c` | `e987de5fe93618c2058dfd4f7b997f4c04d885ef` | `66dce6905dbb7e27d87d94afed8d0fe4bcde7c32` |
| `4a096d54da512174087c12b4093974af1d426f37` | `08d2eb835c0daf419ec5392954a12959fa3f03b6` | `18deee3d2e2ccbdf962ce76032f98830a139c786` |
| `32dc635508eac3d8d48c46272868a7b3599899f9` | `a561bac0a6f8d12bcb84520d033c21fe746b5015` | `ed07d716801a166ffd178f8de1fc9c474872ddb3` |
| `92d9ffc349b2f1113b80f17f83cd11eca2ab605b` | `7cd4cc9fe02ad1384760e2923a72f8a267689326` | `4113adc8724d46c3c7bd7d625a7c0a45acb72d0e` |
| `75a7a6a31eaf01a115d6fcf31edf225f1038a8ba` | `7205e488fd482d6cab6aff34398e7f5a71a8f5ed` | `5a8a7f7627c791a83534156268e7fc9ac8b7f2ab` |
| `8209c42a7a137599b286d24f2e08ae6e08e8365d` | `6b08e1faffc918f610534ce12e5a4b4800525f83` | `e3dc3690b82f4732b82304bd3b444bdb2f91a1cc` |
| `ede57625d329a367738c16d67f5f712a5276f74e` | `358102d98c0fb7dee8d34019b72ee18c356d8d90` | `13c4219fee255824daf5b4deedd100436e6923e2` |
| `97d44bcdfa73709747b29400840cbd070e75e317` | `91a8a1df27d0f56c139b6e6f250d14d7f81f4883` | `e049add453cc5381a1f5c658bdc5a9776163702a` |
| `938b7842fcfb94135fac2ba9713de126df65f39c` | `70bae8b88afcf6786f3979244b5b41d7140bdf47` | `1a5dc87d48cacc355a8bda4d20daa415d0d85626` |
| `679070bf82f97ca11a2ab43144dda67104cd652f` | `6944e30af59a26eaffce91772bf7a8dec46aa459` | `9b11adf7cf5fd5caf25d2ca8257cdb9a57075ba3` |
| `6ffb1989ac3487c1d191f36d0b711c8ba99f1740` | `613a5ae2f2df1f3b9e269bdee9adc5931032b2ac` | `414311b7eb9a9d1f3c3f960e79fec7655eb5e741` |
| `b62b896854c9c110745b17b492df80d20984892f` | `b8fd8ef0f6a9e99f76ca32af8c09241d85e180e9` | `8180101eb037e54735ee89ae93b359983015b12d` |
| `1a8b367b49beeecdddd42dd1d638c76c76c97e82` | `ba9930dc388bb12244194f16d6e117ff8329d21c` | `d289c0388b70bceb281c7cf6459b4de70610fba2` |
| `fdfa9bd157114968215b735983e1f59254faecd5` | `1b5d3d4d23fa4737f18a974aa82befd0609eb1f0` | `82cd84df9329cacb9719b5e77407a0c5682e1ac1` |
| `fc6eb22ffb9f79294c6170eb12ae56c84f20eac4` | `8e26dc78600422d1c4acac5c7cb33296b81eb801` | `5faadb713a8720aedcd3a0020f059407e57740d6` |
| `8352e598331a2897b790958385976e5c421575cf` | `6a0243a2a00c51afe2c89debb90657c5b114db4a` | `1473b42ac8d93386162496bd10db8ccd914c57e5` |
| `40689f80be83b036d34bbbe45acd721cfd2cdb97` | `8e3e7ae796a6d745bd9b6162640a1331b474d887` | `248e5af14798b21d3fa446edbf9ecee13e3dd605` |
| `9ae03e084ca57b10f2e946e1bdd25a18ddf6aa3b` | `0c0706e3a02dea0742c95147985fd548538d7143` | `c091b3bb37d33d17611605059b478e313486c614` |
| `028a351fb7d02c3b1a69289105160f999a1d33ec` | `f0e6fd1020b0e53efe10c38d6589aa22acb0ded4` | `822f20da79a31bf93d984ce61e5165a8567659dd` |
| `b714b61ea11cdb54a610557dcd7c138b06937723` | `33dc0e929ef0eafbd98edf61a5c9db09ee8860e7` | `8b84ea03fa0136c6ee2ca9f98e59228203af881a` |
| `b28401e21ec912db5896878aaad43236d7445d9c` | `070bc214875b3f6c15df3cce5aeabe4c79da3c55` | `d9a307f1993370e1512ef65f8bc98474b363abc5` |
| `0144b87dfbea8ef20530071113309861e13001db` | `e9f09e908d2b0dc613027a7fef1ac5a41dccad7c` | `da44f859ed7d9654bf7c4d3c0473bb7aaf67b58a` |
| `d3ee50a4ca231d3caea3d065172ffe44d315f7eb` | `a26ebc37f8cf13983e462649ec7070beacc017e0` | `3ca3655de29fa1783b47fc87c592fa504dd889a0` |
| `679e785c00798ea6fb6b574a739fef04424484bc` | `e3a0610ef1ea7b51ac73cd5af0f27d8c51a20aff` | `843910b41d426cbbdbb6346a670926c4fbc53687` |
| `e745b2a6a6f146c0028176070bddee0062f849af` | `5aac7aea2e6159a38c72ef3e94c51257a25c2210` | `4cdfe454a77dddad4e773b1efb87e352a6f51c7f` |
| `df88c60ae47b6ea662c5758746ea4c74248d4e0c` | `9b43eee046b3d285734c5532b31c04ff361940b0` | `a313a6bc44a5bf7e6b8d143322daee4cab2669d7` |
| `bf486f1bfc606e0e818ac8ecc3e575799611f821` | `3014413f7124e1a2dc24774372f4398a059ac563` | `42f32bc2d0519d2344763e44f0644ffec7f6163a` |

This correction is limited to Git metadata and parent hashes. It does not
alter any scientific observation or turn a pilot into a replication. The
public GitHub contributor display can lag behind a force-pushed branch.
